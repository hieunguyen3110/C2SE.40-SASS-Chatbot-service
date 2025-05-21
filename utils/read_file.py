import re
import fitz
import json

stop_words = {"và", "là", "của", "the", "một", "trong", "với", "có", "của", "để", "làm", "này", "có thể", "nhưng", "đó"}

class ReadFile:
    def __init__(self,
                 document_file: str="",
                 extension: str="",
                 file_name:str=""
                 ):
        self.file=document_file
        self.extension=extension
        self.file_name=file_name

    def extract_text_by_page(self, doc):
        pages_content = []
        unwanted_chars = r'[^\w\s.,?!\-]'

        for page_num in range(doc.page_count):
            page = doc.load_page(page_num)
            blocks = page.get_text("dict")["blocks"]
            page_text = []

            for block in blocks:
                if block.get("type") == 0:  # Text block
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            cleaned_text = re.sub(unwanted_chars, '', span["text"]).strip()
                            if cleaned_text:
                                page_text.append(cleaned_text)

            combined_text = " ".join(page_text)
            pages_content.append({
                "title": f"Page {page_num + 1}",
                "content": combined_text.lower(),
                "file_name": self.file_name
            })

        return pages_content


    def read_file(self):
        try:
            if self.extension == ".pdf":
                doc = fitz.open(self.file)
                return self.extract_text_by_page(doc)
            else:
                raise ValueError("Unsupported file type")
        except Exception as e:
            print(f"Error reading file: {e}")
            return []

    @staticmethod
    def extract_questions_and_answers(response_text):
        # Bắt đầu xử lý câu hỏi
        question_start = response_text.find('"questions": [')
        question_end = response_text.find(']', question_start) + 1

        # Lấy phần chuỗi chứa tất cả các câu hỏi
        questions_section = response_text[question_start:question_end]
        convert_to_json = f"""
        {{
            {questions_section}
        }}
        """
        data = json.loads(convert_to_json)
        return data["questions"]

    @staticmethod
    def remove_stopwords(words):
        return [word for word in words if word.lower() not in stop_words]


    def clean_and_tokenize(self,text):
        text_clean = re.sub(r'[^\w\s.,;!?-]', '', text)
        words = text_clean.split()
        filtered_words = self.remove_stopwords(words)
        filtered_words = [word for word in filtered_words if len(word) > 1 and word.lower() not in stop_words]
        return filtered_words
