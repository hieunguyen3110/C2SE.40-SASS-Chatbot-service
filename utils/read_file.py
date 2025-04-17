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

    # @staticmethod
    # def extract_text_with_style(self, doc):
    #     text_with_style = []
    #     font_accept = ["Bold", "BoldItal", "BoldMT", "BoldItalicMT"]
    #     current_title = []
    #     current_content = []
    #     unwanted_chars = r'[^\w\s.,?!\-]'
    #     sum_size = 0
    #     count_text = 1
    #
    #     for page_num in range(doc.page_count):
    #         page = doc.load_page(page_num)
    #         blocks = page.get_text("dict")["blocks"]
    #         for block in blocks:
    #             if block.get("type") == 0:  # Text block
    #                 for line in block.get("lines", []):
    #                     for span in line.get("spans", []):
    #                         count_text += 1
    #                         sum_size += span["size"]
    #                         cleaned_text = re.sub(unwanted_chars, '', span["text"]).strip()
    #                         if cleaned_text:
    #                             text_with_style.append({
    #                                 "text": cleaned_text,
    #                                 "font": span["font"],
    #                                 "size": span["size"],
    #                                 "color": span["color"],
    #                                 "bbox": span["bbox"]
    #                             })
    #
    #     average_size = math.ceil(sum_size / count_text)
    #     for item in text_with_style:
    #         font_split = item["font"].split("-") or item["font"].split(",")
    #         is_check = (
    #                 (len(font_split) > 1 and font_split[1] in font_accept) or
    #                 item["color"] != 0 or
    #                 item["size"] >= average_size * 1.25
    #         )
    #
    #         if is_check:
    #             current_title.append(item["text"])
    #         else:
    #             if current_title:
    #                 if len(current_content) > 0 and current_content[-1]["title"] == current_title[-1]:
    #                     current_content[-1]["content"] += f" {item['text']}"
    #                 else:
    #                     current_content.append({
    #                         "title": current_title[-1],
    #                         "content": item["text"],
    #                         "file_name": self.file_name
    #                     })
    #
    #     return current_content


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
