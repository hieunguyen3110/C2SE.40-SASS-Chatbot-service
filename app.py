from mimetypes import guess_extension
import os
from xmlrpc.client import Error

from flask import Flask, jsonify, request, abort
from dotenv import load_dotenv
import requests
from flask_cors import CORS

from db import QueryDB
from rag.core import RAG
from embeddings import EmbeddingConfig, SentenceTransformerEmbedding
from semantic_router import SemanticRouter, Route
from semantic_router.samples import productsSample, chitchatSample
import google.generativeai as genai
from reflection import Reflection
from utils import ReadFile
from langdetect import detect
from PyPDF2 import PdfReader
from tempfile import NamedTemporaryFile
import re



app = Flask(__name__)


load_dotenv()
# CORS(app)
CORS(
    app,
    resources={r"/api/*": {"origins": ["http://localhost:5173", "http://localhost:8088"]}},
    methods=["GET", "POST", "PUT"],
    allow_headers=["Content-Type", "Authorization"],
    supports_credentials=True,
)
# Access the key
MONGODB_URI = "mongodb+srv://hieu3110:Hieu31102003@dbtest.qmykx.mongodb.net/?retryWrites=true&w=majority&tls=true&tlsAllowInvalidCertificates=true&appName=dbtest&serverSelectionTimeoutMS=5000"
DB_NAME = "vector_db"
DB_COLLECTION = "documents"
LLM_KEY = "AIzaSyCWvC0YT21YdAfFQgM9Si7Ad7mNK1PINgA"
# EMBEDDING_MODEL = 'keepitreal/vietnamese-sbert'
EMBEDDING_MODEL= 'sentence-transformers/all-mpnet-base-v2'

# --- Semantic Router Setup --- #

PRODUCT_ROUTE_NAME = 'products'
CHITCHAT_ROUTE_NAME = 'chitchat'

embeddingConfig= EmbeddingConfig(name=EMBEDDING_MODEL)
productRoute = Route(name=PRODUCT_ROUTE_NAME, samples=productsSample)
chitchatRoute = Route(name=CHITCHAT_ROUTE_NAME, samples=chitchatSample)
semanticRouter = SemanticRouter(embedding=SentenceTransformerEmbedding(config=embeddingConfig), routes=[productRoute, chitchatRoute])

with open("/Users/pro/Documents/CAPSTONE2/sass-microservice/Chatbot-service/resources/sensitive-words.txt", "r", encoding="utf-8") as f:
    sensitive_words = set(line.strip().lower() for line in f if line.strip())
# --- End Semantic Router Setup --- #


# --- Set up LLMs --- #

genai.configure(api_key=LLM_KEY)
llm = genai.GenerativeModel('gemini-1.5-pro')

# --- End Set up LLMs --- #

# --- Relection Setup --- #

reflection = Reflection(llm=llm)

# --- End Reflection Setup --- #


# Initialize RAG
rag = RAG(
    mongodbUri=MONGODB_URI,
    dbName=DB_NAME,
    dbCollection=DB_COLLECTION,
    embeddingName=EMBEDDING_MODEL,
    llm=llm,
    importance_feature=None
)

query_db= QueryDB(mongodbUri=MONGODB_URI,
    dbName=DB_NAME,
    dbCollection=DB_COLLECTION,)


def process_query(query):
    return query.lower()


def call_llm_query(user_query, prompt):
    data_with_roles = [
        {"role": "user", "parts": [{"text": user_query}]},
        # Add role to original user message
        {"role": "user", "parts": [{"text": prompt}]}
    ]
    response = rag.generate_content(data_with_roles)

    return response


@app.route('/api/search', methods=['POST'])
def handle_query():
    try:
        data = [request.get_json()]
        allow_language = ["vi", "en", "fi"]
        query = data[-1]["parts"][0]["text"]
        check_lang = detect(query)
        if check_lang not in allow_language:
            return jsonify({'error': 'Language not allowed'}), 400

        query = process_query(query)

        if not query:
            return jsonify({'error': 'No query provided'}), 400

        # get last message

        guidedRoute = semanticRouter.guide(query)[1]
        file_source = []
        if guidedRoute == PRODUCT_ROUTE_NAME:
            # Decide to get new info or use previous info
            # Guide to RAG system
            print("Guide to RAGs")

            reflected_query = reflection(data)

            query = reflected_query
            source_information = rag.enhance_prompt(query, file_source).replace('<br>', '\n')
            combined_information = f"Hãy trở thành chuyên gia trợ lý ảo hỗ trợ học tập. Câu hỏi của người dùng: {query}\nTrả lời câu hỏi dựa vào các thông tin dưới đây: {source_information}."
            response = call_llm_query(data[-1]["parts"][0]["text"], combined_information)
        else:
            # Guide to LLMs
            print("Guide to LLMs")
            response = llm.generate_content(data)

        return jsonify({
            'parts': [
                {
                    'text': response.text,
                    'file_source': file_source
                }
            ],
            'role': 'model'
        })
    except requests.exceptions.RequestException as e:
        abort(401, description=f"Something went wrong: {e}")

@app.route('/api/clear-data')
def hello_world():
    # put application's code here
    query_db.clear_data()
    return jsonify({
        "message": "clear data successful"
    })


@app.route("/api/upload-file", methods=['POST'])
def send_file():
    try:
        # Fetch the file
        data= request.get_json()
        file_url= data.get("filePath")
        file_name = data.get("fileName")
        response = requests.get(file_url)
        if response.status_code != 200:
            abort(404, description="File not found or inaccessible")

        # Check content type and determine file extension
        content_type_res = response.headers.get('Content-Type')
        if content_type_res:
            extension = guess_extension(content_type_res.split(";")[0])
            if extension in ['.pdf', '.docx']:
                temp_file_path = f"/Users/pro/Documents/CAPSTONE1/chatbotRAG/resources/temp_download_file{extension}"
                # Save the file locally
                with open(temp_file_path, "wb") as f:
                    f.write(response.content)

                # Process the file
                result = ReadFile(document_file=temp_file_path, extension=extension,file_name=file_name)
                processed_result = result.read_file()
                for content in processed_result:
                    embeddings = rag.get_embedding(content["content"])
                    content["embeddings"] = embeddings

                query_db.insert_data(processed_result)
                return jsonify({"message": "File processed successfully", "result": processed_result}), 200
            else:
                abort(400, description="File type not valid")
        else:
            abort(400, description="Content-Type not found in response headers")
    except requests.exceptions.RequestException as e:
        abort(401, description=f"Something went wrong: {e}")

@app.route("/api/check-file", methods=['POST'])
def check_file():
    try:
        # Lấy dữ liệu từ request
        data = request.get_json()
        file_url = data.get("filePath")
        if not file_url:
            return jsonify({"error": "File URL is required"}), 400

        # Tải file từ URL
        response = requests.get(file_url)
        if response.status_code != 200:
            return jsonify({"error": "Failed to fetch file from URL"}), 404

        # Kiểm tra loại file
        content_type = response.headers.get('Content-Type')
        if not content_type or 'application/pdf' not in content_type:
            return jsonify({"error": "Only PDF files are supported"}), 400

        # Lưu file tạm thời
        with NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
            temp_file.write(response.content)
            temp_file_path = temp_file.name

        # Đọc file PDF
        try:
            reader = PdfReader(temp_file_path)
            text = ""
            for page in reader.pages:
                text += page.extract_text()
        except Exception as e:
            return jsonify({"error": "Failed to read PDF file", "details": str(e)}), 500
        finally:
            # Xóa file tạm sau khi xử lý
            os.remove(temp_file_path)

        # Tách văn bản thành các từ
        words_in_text = set(re.findall(r'\b\w+\b', text.lower()))

        # Kiểm tra các từ nhạy cảm
        found_words = words_in_text.intersection(sensitive_words)
        print(found_words)
        if found_words:
            return jsonify({"containsSensitiveWords": True, "sensitiveWords": list(found_words)}), 200
        else:
            return jsonify({"containsSensitiveWords": False}), 200

    except requests.exceptions.RequestException as e:
        return jsonify({"error": "Error while fetching the file", "details": str(e)}), 400
    except Exception as e:
        return jsonify({"error": "An unexpected error occurred", "details": str(e)}), 500

@app.route("/api/v1/get-solutions", methods=['POST'])
def handle_offer_improved_solutions():
    try:
        data = request.get_json()
        # Tách Final Grade ra
        final_grade = data.pop("Final Grade")

        # Chuyển đổi thành key: value
        flattened_data = {key: list(value.values())[0] for key, value in data.items()}

        print(flattened_data)

        strengths, weakness = rag.identify_strengths_weaknesses(flattened_data)

        print(strengths, weakness)

        prompt = rag.create_prompt_predict_score(flattened_data, final_grade, strengths, weakness)

        response = call_llm_query("get solution for student", prompt)

        return jsonify(
            {
                "code": 200,
                "message": "success",
                "data": response.text
            }
        )
    except Error as e:
        abort(400, "Error when providing solutions for students.")


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002, debug=True)


