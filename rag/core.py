import pymongo
from IPython.display import Markdown
import textwrap
from embeddings import SentenceTransformerEmbedding, EmbeddingConfig

class RAG:
    def __init__(self, 
            mongodbUri: str,
            dbName: str,
            dbCollection: str,
            llm,
            embeddingName: str = 'sentence-transformers/all-mpnet-base-v2',
            importance_feature=None
        ):
        if importance_feature is None:
            self.importance_feature = ["Study_Hours_per_Week", "Assignment_Completion_Rate (%)", "Exam_Score (%)"]
        self.client = pymongo.MongoClient(mongodbUri)
        self.db = self.client[dbName] 
        self.collection = self.db[dbCollection]
        self.embedding_model = SentenceTransformerEmbedding(
            EmbeddingConfig(name=embeddingName)
        )
        self.llm = llm

    def get_embedding(self, text):
        if not text.strip():
            return []

        embedding = self.embedding_model.encode(text)
        return embedding.tolist()

    def vector_search(
            self, 
            user_query: str, 
            limit=4,
            file_filter=None):
        """
        Perform a vector search in the MongoDB collection based on the user query.

        Args:
        user_query (str): The user's query string.

        Returns:
        list: A list of matching documents.
        """

        # Generate embedding for the user query
        query_embedding = self.get_embedding(user_query)

        if query_embedding is None:
            return "Invalid query or embedding generation failed."

        vector_search_stage = {
            "$vectorSearch": {
                "index": "vector_index",
                "queryVector": query_embedding,
                "path": "embeddings",
                "numCandidates": 1000,
                "limit": limit,
                "scoreThreshold": 0.75
            }
        }
        # Optional: lọc theo file
        if file_filter:
            vector_search_stage["$vectorSearch"]["filter"] = {"file_name": file_filter}

        unset_stage = {
            "$unset": "embeddings"
        }

        project_stage = {
            "$project": {
                "_id": 0,  
                "title": 1,
                "doc_id": 1,
                "content": 1,
                "file_name":1,
                "score": {
                    "$meta": "vectorSearchScore"
                }
            }
        }

        pipeline = [vector_search_stage, unset_stage, project_stage]

        # Execute the search
        results = self.collection.aggregate(pipeline)
        return list(results)

    def enhance_prompt(self, query,file_source):
        get_knowledge = self.vector_search(query.text, 10)
        enhanced_prompt = ""
        for i, result in enumerate(get_knowledge, start=1):
            title = result.get("title", f"Không rõ trang {i}")
            file_name = result.get("file_name")
            content = result.get("content", "hiện tại, tôi chưa biết về câu hỏi")

            # Gộp prompt theo thứ tự gọn gàng
            enhanced_prompt += f"\n {i}) Nội dung ở trang: {title}"

            if file_name:
                file_source.append(file_name)
                print(f"Appended file_name: {file_name}")
                enhanced_prompt += f", tham chiếu từ tài liệu: {file_name}"

            enhanced_prompt += f", nội dung: {content}"
        return enhanced_prompt

    def generate_content(self, prompt):
        return self.llm.generate_content(prompt)

    @staticmethod
    def _to_markdown(text):
        text = text.replace('•', '  *')
        return Markdown(textwrap.indent(text, '> ', predicate=lambda _: True))

    def create_prompt_predict_score(self, student_data, score, strengths, weaknesses):
        filtered_data = {key: student_data[key] for key in self.importance_feature if key in student_data}
        top_features = sorted(filtered_data.items(), key=lambda x: x[1], reverse=True)[:3]
        important_factors = [f"{feature.replace('_', ' ')}" for feature, _ in top_features]
        convertParticipateIn = "Yes" if student_data.get('Participation_in_Discussions') == 0 else "No"

        prompt = f"""
        Bạn là một cố vấn học tập chuyên nghiệp. Hãy đưa ra những đề xuất cá nhân hóa và chính xác để giúp sinh viên cải thiện kết quả học tập dựa trên dữ liệu sau:

        ## Thông tin sinh viên
        - Số khóa học trực tuyến đã hoàn thành: {student_data.get('Online_Courses_Completed', 'N/A')}
        - Mức độ tham gia thảo luận: {convertParticipateIn}
        - Tỷ lệ hoàn thành bài tập: {student_data.get('Assignment_Completion_Rate (%)', 'N/A')}%
        - Điểm kiểm tra: {student_data.get('Exam_Score (%)', 'N/A')}%

        ## Dự đoán kết quả
        - Mức điểm chữ: {score} trên thang điểm A, B, C, D, F

        ## Điểm mạnh
        {chr(10).join([f"- {s}" for s in strengths]) if strengths else "- Không có thông tin"}

        ## Điểm yếu cần cải thiện
        {chr(10).join([f"- {w}" for w in weaknesses]) if weaknesses else "- Không có thông tin"}

        ## Các yếu tố ảnh hưởng lớn nhất đến kết quả
        {chr(10).join([f"- {f}" for f in important_factors])}

        Dựa trên thông tin này, hãy đưa ra:
        1. Giới hạn câu trả lời trong khoảng 500-600 từ, Đưa ra đề xuất phương pháp cải thiện không trả lời lan man.
        2. Đánh giá ngắn gọn về tình hình học tập hiện tại của sinh viên
        3. 3-5 đề xuất cụ thể để cải thiện điểm số, tập trung vào các điểm yếu và yếu tố ảnh hưởng lớn nhất
        4. Kế hoạch học tập theo tuần với các mục tiêu ngắn hạn và dài hạn để cải thiện điểm
        5. Đề xuất về cách thức theo dõi tiến độ và điều chỉnh phương pháp học tập

        Lưu ý: Hãy đưa ra những đề xuất thực tế và khả thi, phù hợp với phong cách học của sinh viên. Các đề xuất nên cụ thể và có thể hành động được.
        """
        return prompt

    @staticmethod
    def create_prompt_learning_analyze(student_data, score, course_periods, subject_weakens):
        convertParticipateIn = "Yes" if student_data.get('Participation_in_Discussions') == 0 else "No"
        course_period_names = [item["subject_name"] for item in course_periods]
        subject_weakens_names = [{
            "subject_name": item["subject_name"],
            "average_score": item["avg_score"]
        } for item in subject_weakens]
        prompt = f"""
        Bạn là một trợ lý học tập thông minh có khả năng phân tích dữ liệu học tập của sinh viên và đưa ra những đề xuất cá nhân hóa để cải thiện kết quả học tập. Hãy phân tích dữ liệu sau đây:

        1. Danh sách các môn học yếu: {subject_weakens_names}
        2. Các môn học trong kỳ: {str(course_period_names)}
        3. Dự đoán điểm cuối kỳ: {score} trên thang điểm A, B, C, D, F
        4. Dữ liệu học tập:
           - Số lượng khóa học online đã hoàn thành: {student_data.get('Online_Courses_Completed', 'N/A')}
           - Tham gia vào nhóm học tập: {convertParticipateIn}
           - Tỷ lệ hoàn thành bài tập: {student_data.get('Assignment_Completion_Rate (%)', 'N/A')}%
           - Điểm trung bình các bài kiểm tra: {student_data.get('Exam_Score (%)', 'N/A')}%
        
        Dựa trên thông tin này, hãy tạo một phân tích toàn diện bao gồm các phần sau, định dạng JSON:
        
        ```
        {{
          "general_assessment": {{
            "overall_status": "Đánh giá tổng quan về tình hình học tập hiện tại",
            "strengths": ["Điểm mạnh 1", "Điểm mạnh 2", "..."],
            "weaknesses": ["Điểm yếu 1", "Điểm yếu 2", "..."],
            "risk_assessment": "Đánh giá nguy cơ học tập dựa trên các dữ liệu"
          }},
          "improvement_suggestions": [
            {{
              "focus_area": "Lĩnh vực cần cải thiện",
              "specific_action": "Hành động cụ thể để cải thiện",
              "expected_outcome": "Kết quả dự kiến từ việc thực hiện đề xuất"
            }},
            // 2-3 đề xuất tương tự
          ],
          "weekly_study_plan": {{
            "short_term_goals": ["Mục tiêu ngắn hạn 1", "Mục tiêu ngắn hạn 2", "..."],
            "long_term_goals": ["Mục tiêu dài hạn 1", "Mục tiêu dài hạn 2", "..."],
            "daily_schedule": {{
              "monday": {{
                "focus_subjects": ["Môn học 1", "Môn học 2"],
                "recommended_activities": ["Hoạt động 1", "Hoạt động 2"],
                "study_hours": "Khung giờ đề xuất",
              }},
              "tuesday": {{
                "focus_subjects": ["Môn học 1", "Môn học 2"],
                "recommended_activities": ["Hoạt động 1", "Hoạt động 2"],
                "study_hours": "Khung giờ đề xuất",
              }},
              "wednesday": {{
                "focus_subjects": ["Môn học 1", "Môn học 2"],
                "recommended_activities": ["Hoạt động 1", "Hoạt động 2"],
                "study_hours": "Khung giờ đề xuất",
              }},
              "thursday": {{
                "focus_subjects": ["Môn học 1", "Môn học 2"],
                "recommended_activities": ["Hoạt động 1", "Hoạt động 2"],
                "study_hours": "Khung giờ đề xuất",
              }},
              "friday": {{
                "focus_subjects": ["Môn học 1", "Môn học 2"],
                "recommended_activities": ["Hoạt động 1", "Hoạt động 2"],
                "study_hours": "Khung giờ đề xuất",
              }},
              "saturday": {{
                "focus_subjects": ["Môn học 1", "Môn học 2"],
                "recommended_activities": ["Hoạt động 1", "Hoạt động 2"],
                "study_hours": "Khung giờ đề xuất",
              }},
            }}
          }},
          "progress_tracking": {{
            "metrics_to_monitor": ["Chỉ số theo dõi 1", "Chỉ số theo dõi 2", "..."],
            "adjustment_strategies": ["Chiến lược điều chỉnh 1", "Chiến lược điều chỉnh 2", "..."]
          }}
        }}
        ```
        
        Lưu ý:
        1. Hãy đưa ra đánh giá dựa trên mối tương quan giữa các yếu tố và ảnh hưởng của chúng đến kết quả học tập.
        2. Đưa ra các đề xuất cụ thể, phù hợp với điểm yếu đã xác định.
        3. Kế hoạch học tập phải khả thi và tập trung vào việc cải thiện các môn học yếu.
        4. Đề xuất các tài liệu học tập phù hợp với từng môn học và điểm yếu cụ thể.
        5. Chiến lược theo dõi tiến độ phải đo lường được và có thể điều chỉnh khi cần thiết.
        """
        return prompt

    @staticmethod
    def create_prompt_get_question(words, n=5):
        prompt = f"""
        Dưới đây là danh sách các từ quan trọng được trích xuất từ văn bản gốc. Dựa trên những từ này, vui lòng tạo ra ít nhất {n} câu hỏi trắc nghiệm với cấu trúc rõ ràng, dễ dàng cho hệ thống front-end trích xuất. Mỗi câu hỏi cần có 4 lựa chọn (A, B, C, D), trong đó chỉ có một câu trả lời đúng.

        Định dạng trả về câu hỏi:
        {{
            "questions": [
                {{
                    "question": "Câu hỏi 1?",
                    "options": {{
                        "A": "Lựa chọn A",
                        "B": "Lựa chọn B",
                        "C": "Lựa chọn C",
                        "D": "Lựa chọn D"
                    }},
                    "correct_answer": "A"
                }},
                {{
                    "question": "Câu hỏi 2?",
                    "options": {{
                        "A": "Lựa chọn A",
                        "B": "Lựa chọn B",
                        "C": "Lựa chọn C",
                        "D": "Lựa chọn D"
                    }},
                    "correct_answer": "B"
                }},
                ...
            ]
        }}

        Danh sách từ đã trích xuất:
        {words}

        Lưu ý:
        - Tạo ít nhất {n} câu hỏi trắc nghiệm.
        - Nếu có thể tạo ra nhiều câu hỏi hơn, mặc định hãy tạo {n} câu hỏi.
        - Đảm bảo các câu hỏi có tính chất thách thức và không dễ dàng đoán được đáp án đúng.
        - Câu trả lời đúng phải được xác định rõ trong mỗi câu hỏi.
        - Câu hỏi có thể xoay quanh các định nghĩa, khái niệm, hoặc ứng dụng của các từ được trích xuất.
        """

        return prompt

    @staticmethod
    def identify_strengths_weaknesses(student_data):
        """Xác định điểm mạnh và điểm yếu dựa trên dữ liệu sinh viên"""
        strengths = []
        weaknesses = []

        # Các ngưỡng đánh giá (có thể tùy chỉnh)
        thresholds = {
            'Online_Courses_Completed': {'low': 2, 'high': 5},
            'Participation_in_Discussions': {'low': "No", 'high': "Yes"},
            'Assignment_Completion_Rate': {'low': 70, 'high': 80},
            'Exam_Score': {'low': 70, 'high': 80},
        }

        for feature, value in student_data.items():
            if feature in thresholds:
                threshold = thresholds[feature]
                if feature == 'Participation_in_Discussions':
                    if value == threshold['low']:
                        weaknesses.append(f"{feature}: {value}")
                    elif value == threshold['high']:
                        strengths.append(f"{feature}: {value}")
                else:
                    if value > threshold['high']:
                        strengths.append(f"{feature}: {value}")
                    elif value < threshold['low']:
                        weaknesses.append(f"{feature}: {value}")

        return strengths, weaknesses


