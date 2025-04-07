import re
import math
import fitz
from numpy.ma.extras import average


class ReadFile:
    def __init__(self,
                 document_file: str,
                 extension: str,
                 file_name:str
                 ):
        self.file=document_file
        self.extension=extension
        self.file_name=file_name

    # @staticmethod
    # def extract_text_with_style(self,doc):
    #     text_with_style = []
    #     unwanted_chars = r'[^a-zA-Z\s]'
    #     font_accept = ["Bold", "BoldItal", "BoldMT", "BoldItalicMT"]
    #     current_title = []
    #     current_content = []
    #     sum_size=0
    #     count_text=1
    #     for page_num in range(doc.page_count):
    #         page = doc.load_page(page_num)
    #         blocks = page.get_text("dict")["blocks"]
    #         for block in blocks:
    #             if "lines" in block:
    #                 for line in block["lines"]:
    #                     for span in line["spans"]:
    #                         count_text+=1
    #                         sum_size+=span["size"]
    #                         text_with_style.append({
    #                             "text": span["text"],
    #                             "font": span["font"],  # Phong cách chữ (bold, italic, v.v.)
    #                             "size": span["size"],
    #                             "color": span["color"]  # Kích thước chữ
    #                         })
    #     average_size= math.ceil(sum_size/count_text)
    #     count = -1
    #     for item in text_with_style:
    #         font_split = item["font"].split("-") or item["font"].split(",")
    #         is_check = False
    #         if (
    #                 # len(font_split) > 1 and
    #                 # item["size"] >= average_size and
    #                 (( len(font_split)>1 and font_split[1] in font_accept) or
    #                  item["color"] != 0 or
    #                  item["size"] >= average_size*1.25 ) and
    #                 not re.match(unwanted_chars, item['text'])):
    #             count += 1
    #             is_check = True
    #             current_title.append(item["text"])
    #
    #         if not is_check:
    #             if len(current_content)>0 and current_content[-1]["title"] == current_title[count]:
    #                 current_content[-1]["content"]+=item["text"]
    #             else:
    #                 if count>=0:
    #                     current_content.append({
    #                         "title": current_title[count],
    #                         "content": item["text"],
    #                         "file_name": self.file_name
    #                     })
    #
    #     # with open("/Users/pro/Documents/CAPSTONE1/chatbotRAG/resources/title.txt","w") as f:
    #     #     f.write("\n".join(current_title))
    #     #
    #     # with open("/Users/pro/Documents/CAPSTONE1/chatbotRAG/resources/content.txt","w") as f:
    #     #     for item in current_content:
    #     #         f.write("%s\n" % item["content"])
    #
    #     # print(current_title)
    #     # print(current_content)
    #     return current_content

    # @staticmethod
    def extract_text_with_style(self, doc):
        text_with_style = []
        font_accept = ["Bold", "BoldItal", "BoldMT", "BoldItalicMT"]
        current_title = []
        current_content = []
        unwanted_chars = r'[^\w\s.,?!\-]'
        sum_size = 0
        count_text = 1

        for page_num in range(doc.page_count):
            page = doc.load_page(page_num)
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if block.get("type") == 0:  # Text block
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            count_text += 1
                            sum_size += span["size"]
                            cleaned_text = re.sub(unwanted_chars, '', span["text"]).strip()
                            if cleaned_text:
                                text_with_style.append({
                                    "text": cleaned_text,
                                    "font": span["font"],
                                    "size": span["size"],
                                    "color": span["color"],
                                    "bbox": span["bbox"]
                                })

        average_size = math.ceil(sum_size / count_text)
        for item in text_with_style:
            font_split = item["font"].split("-") or item["font"].split(",")
            is_check = (
                    (len(font_split) > 1 and font_split[1] in font_accept) or
                    item["color"] != 0 or
                    item["size"] >= average_size * 1.25
            )

            if is_check:
                current_title.append(item["text"])
            else:
                if current_title:
                    if len(current_content) > 0 and current_content[-1]["title"] == current_title[-1]:
                        current_content[-1]["content"] += f" {item['text']}"
                    else:
                        current_content.append({
                            "title": current_title[-1],
                            "content": item["text"],
                            "file_name": self.file_name
                        })

        return current_content


    def read_file(self):
        try:
            if self.extension == ".pdf":
                doc = fitz.open(self.file)
                return self.extract_text_with_style(doc)
            else:
                raise ValueError("Unsupported file type")
        except Exception as e:
            print(f"Error reading file: {e}")
            return []
