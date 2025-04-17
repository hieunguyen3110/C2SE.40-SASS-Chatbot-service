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
            # embeddingName: str ='keepitreal/vietnamese-sbert',
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

        # Define the vector search pipeline
        # vector_search_stage = {
        #     "$vectorSearch": {
        #         "index": "vector_index",
        #         "queryVector": query_embedding,
        #         "path": "embeddings",
        #         "numCandidates": 500,
        #         "limit": limit,
        #     }
        # }
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
        i = 0
        # for result in get_knowledge:
        #     if result.get('title'):
        #         i += 1
        #         enhanced_prompt += f"\n {i}) Nội dung ở trang: {result.get('title')}"
        #         if result.get('file_name'):
        #             file_source.append(result.get('file_name'))
        #             print(f"Appended file_name: {result.get('file_name')}")  # Debug
        #             enhanced_prompt += f", tham chiếu từ tài liệu : {result.get('file_name')}"
        #
        #         if result.get('content'):
        #             enhanced_prompt += f", nội dung : {result.get('content')}"
        #         else:
        #             enhanced_prompt += f", hiện tại, tôi chưa biết về câu hỏi"
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

        prompt = f"""
        Bạn là một cố vấn học tập chuyên nghiệp. Hãy đưa ra những đề xuất cá nhân hóa và chính xác để giúp sinh viên cải thiện kết quả học tập dựa trên dữ liệu sau:

        ## Thông tin sinh viên
        - Thời gian học mỗi tuần: {student_data.get('Study_Hours_per_Week', 'N/A')} giờ
        - Phong cách học ưa thích: {student_data.get('Preferred_Learning_Style', 'N/A')}
        - Số khóa học trực tuyến đã hoàn thành: {student_data.get('Online_Courses_Completed', 'N/A')}
        - Mức độ tham gia thảo luận: {student_data.get('Participation_in_Discussions', 'N/A')}/10
        - Tỷ lệ hoàn thành bài tập: {student_data.get('Assignment_Completion_Rate (%)', 'N/A')}%
        - Điểm kiểm tra: {student_data.get('Exam_Score (%)', 'N/A')}%
        - Thời gian dùng mạng xã hội mỗi tuần: {student_data.get('Time_Spent_on_Social_Media (hours/week)', 'N/A')} giờ
        - Số giờ ngủ mỗi đêm: {student_data.get('Sleep_Hours_per_Night', 'N/A')} giờ

        ## Dự đoán kết quả
        - Mức điểm chữ: {score} trên thang điểm A, B, C, D, F

        ## Điểm mạnh
        {chr(10).join([f"- {s}" for s in strengths]) if strengths else "- Không có thông tin"}

        ## Điểm yếu cần cải thiện
        {chr(10).join([f"- {w}" for w in weaknesses]) if weaknesses else "- Không có thông tin"}

        ## Các yếu tố ảnh hưởng lớn nhất đến kết quả
        {chr(10).join([f"- {f}" for f in important_factors])}

        Dựa trên thông tin này, hãy đưa ra:
        1. Đánh giá ngắn gọn về tình hình học tập hiện tại của sinh viên
        2. 3-5 đề xuất cụ thể để cải thiện điểm số, tập trung vào các điểm yếu và yếu tố ảnh hưởng lớn nhất
        3. Kế hoạch học tập theo tuần với các mục tiêu ngắn hạn và dài hạn để cải thiện điểm
        4. Đề xuất về cách thức theo dõi tiến độ và điều chỉnh phương pháp học tập

        Lưu ý: Hãy đưa ra những đề xuất thực tế và khả thi, phù hợp với phong cách học của sinh viên. Các đề xuất nên cụ thể và có thể hành động được.
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
            'Study_Hours_per_Week': {'low': 12, 'high': 20},
            'Online_Courses_Completed': {'low': 2, 'high': 5},
            'Participation_in_Discussions': {'low': "No", 'high': "Yes"},  # Giả sử thang điểm 0-10
            'Assignment_Completion_Rate': {'low': 70, 'high': 80},
            'Exam_Score': {'low': 70, 'high': 80},
            'Time_Spent_on_Social_Media': {'low': 14, 'high': 21},  # Ngược lại: ít hơn là tốt
            'Sleep_Hours_per_Night': {'low': 5, 'high': 7}
        }

        for feature, value in student_data.items():
            if feature == 'Preferred_Learning_Style':
                continue  # Bỏ qua phong cách học vì không phải điểm mạnh/yếu

            if feature in thresholds:
                threshold = thresholds[feature]

                # Xử lý đặc biệt cho Time_Spent_on_Social_Media (ít hơn là tốt)
                if feature == 'Time_Spent_on_Social_Media':
                    if value < threshold['low']:
                        strengths.append(f"{feature}: {value}")
                    elif value > threshold['high']:
                        weaknesses.append(f"{feature}: {value}")
                elif feature == 'Participation_in_Discussions':
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


