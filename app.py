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
from request.CheckFileRequest import CheckFileRequest
from request.UploadFileRequest import UploadFileRequest
from response.ApiRespone import ApiResponse
from semantic_router import SemanticRouter, Route
from semantic_router.samples import productsSample, chitchatSample
import google.generativeai as genai
from reflection import Reflection
from utils import ReadFile
from langdetect import detect
from PyPDF2 import PdfReader
from tempfile import NamedTemporaryFile
import re
import json



app = Flask(__name__)


load_dotenv()
# CORS(app)
CORS(
    app,
    resources={r"/api/*": {"origins": ["http://localhost:5173", "http://localhost:8088", "http://localhost:8084", "http://dtuforyou.xyz", "https://dtuforyou.xyz"]}},
    methods=["GET", "POST", "PUT"],
    allow_headers=["Content-Type", "Authorization"],
    supports_credentials=True,
)
# Access the key
MONGODB_URI = "mongodb+srv://hieu3110:Hieu31102003@dbtest.qmykx.mongodb.net/?retryWrites=true&w=majority&tls=true&tlsAllowInvalidCertificates=true&appName=dbtest&serverSelectionTimeoutMS=5000"
DB_NAME = "vector_db"
DB_COLLECTION = "documents"
LLM_KEY = "AIzaSyCWvC0YT21YdAfFQgM9Si7Ad7mNK1PINgA"
EMBEDDING_MODEL= 'sentence-transformers/all-mpnet-base-v2'

# --- Semantic Router Setup --- #
PRODUCT_ROUTE_NAME = 'products'
CHITCHAT_ROUTE_NAME = 'chitchat'
BASE_URL="/api/v1/chatbot"

embeddingConfig= EmbeddingConfig(name=EMBEDDING_MODEL)
productRoute = Route(name=PRODUCT_ROUTE_NAME, samples=productsSample)
chitchatRoute = Route(name=CHITCHAT_ROUTE_NAME, samples=chitchatSample)
semanticRouter = SemanticRouter(embedding=SentenceTransformerEmbedding(config=embeddingConfig), routes=[productRoute, chitchatRoute])

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SENSITIVE_WORDS_PATH = os.path.join(BASE_DIR, "resources", "sensitive-words.txt")
TEMP_FILE_PATH = os.path.join(BASE_DIR, "resources", "temp_download_file")

with open(SENSITIVE_WORDS_PATH, "r", encoding="utf-8") as f:
    sensitive_words = set(line.strip().lower() for line in f if line.strip())
# --- End Semantic Router Setup --- #

# --- Set up LLMs --- #
genai.configure(api_key=LLM_KEY)
llm = genai.GenerativeModel('gemini-2.0-flash')
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


@app.route(f'{BASE_URL}/search', methods=['POST'])
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
        if guidedRoute == PRODUCT_ROUTE_NAME and len(str(query))>10:
            # Decide to get new info or use previous info
            # Guide to RAG system
            print("Guide to RAGs")

            reflected_query = reflection(data)

            query = reflected_query
            source_information = rag.enhance_prompt(query, file_source).replace('<br>', '\n')
            combined_information = f"Hãy trở thành chuyên gia trợ lý ảo hỗ trợ học tập. Câu hỏi của người dùng: {query}\nTrả lời câu hỏi dựa vào các thông tin dưới đây: {source_information}."
            result = call_llm_query(data[-1]["parts"][0]["text"], combined_information)
            review_prompt = rag.create_prompt_review(query,source_information,result.text)
            response = call_llm_query(result.text,review_prompt)
            clean_answer = re.sub(r"^```json\s*|```$", "", response.text.strip())
            print(clean_answer)
            response = json.loads(clean_answer)
            return ApiResponse.success(data={
                "query": response,
                "file_source": file_source,
            })
        else:
            # Guide to LLMs
            print("Guide to LLMs")
            response = llm.generate_content(data)
            return ApiResponse.success(data={
                "query": {
                    "improved_answer": response.text,
                    "reference_document": None
                },
                "file_source": [],
            })

    except requests.exceptions.RequestException as e:
        abort(401, description=f"Something went wrong: {e}")

@app.route(f'{BASE_URL}/clear-data')
def clear_data():
    # put application's code here
    query_db.clear_data()
    return jsonify({
        "message": "clear data successful"
    })

@app.route(f"{BASE_URL}/upload-file", methods=['POST'])
def send_file():
    try:
        # Fetch the file
        data= request.get_json()
        if not data:
            return ApiResponse.error(message="No data provided", code=400)
        data_request= UploadFileRequest(**data)
        file_url= data_request.filePath
        file_name = data_request.fileName
        response = requests.get(file_url)
        if response.status_code != 200:
            return ApiResponse.error(message="File not found or inaccessible", code=404)

        # Check content type and determine file extension
        content_type_res = response.headers.get('Content-Type')
        if content_type_res:
            extension = guess_extension(content_type_res.split(";")[0])
            if extension in ['.pdf', '.docx']:
                temp_file_path = TEMP_FILE_PATH + extension
                # Save the file locally
                with open(temp_file_path, "wb") as f:
                    f.write(response.content)
                # Process the file
                result = ReadFile(document_file=temp_file_path, extension=extension,file_name=file_name)
                processed_result = result.read_file()
                for content in processed_result:
                    embeddings = rag.get_embedding(content["content"])
                    content["embeddings"] = embeddings
                    content["doc_id"]=data_request.docId

                query_db.insert_data(processed_result)
                return ApiResponse.success(message="File processed successfully",
                                           data="Upload file success")
            else:
                return ApiResponse.error(message="File type not supported", code=400)
        else:
            return ApiResponse.error(message="Content-Type not found in response headers",code=400)
    except requests.exceptions.RequestException as e:
        return ApiResponse.error(message=f"Something went wrong: {str(e)}", code=401)

@app.route(f"{BASE_URL}/check-file", methods=['POST'])
def check_file():
    try:
        # Lấy dữ liệu từ request
        data = request.get_json()
        if not data:
            return ApiResponse.error(message="No file provided", code=400)
        data_request = CheckFileRequest(**data)
        if not data_request.filePath:
            return ApiResponse.error(message="File URL is required", code=400)

        # Tải file từ URL
        response = requests.get(data_request.filePath)
        if response.status_code != 200:
            print(response)
            return ApiResponse.error(message="Failed to fetch file from URL", code=404)

        # Kiểm tra loại file
        content_type = response.headers.get('Content-Type')
        if not content_type or 'application/pdf' not in content_type:
            return ApiResponse.error(message="Only PDF files are supportedL", code=400)

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
            return ApiResponse.error(message=f"Failed to read PDF file: {str(e)}", code=500)
        finally:
            # Xóa file tạm sau khi xử lý
            os.remove(temp_file_path)

        # Tách văn bản thành các từ
        words_in_text = set(re.findall(r'\b\w+\b', text.lower()))

        # Kiểm tra các từ nhạy cảm
        found_words = words_in_text.intersection(sensitive_words)
        print(found_words)
        if found_words:
            return ApiResponse.success(data= {"containsSensitiveWords": True, "sensitiveWords": list(found_words)})
        else:
            return ApiResponse.success(data={"containsSensitiveWords": False, "sensitiveWords": None})

    except requests.exceptions.RequestException as e:
        return ApiResponse.error(message=f"Error while fetching the file: {str(e)}", code=400)
    except Exception as e:
        return ApiResponse.error(message=f"An unexpected error occurred: {str(e)}", code=500)

@app.route(f"{BASE_URL}/get-solutions", methods=['POST'])
def handle_offer_improved_solutions():
    try:
        data = request.get_json()
        # Tách Final Grade ra
        final_grade = data.pop("Final Grade")
        subject_weakens_dict = data.pop("subject_weakens")
        courses_period = data.pop("courses_period")
        subject_weakens_array = [v for v in subject_weakens_dict["subject_weaken_dict"].values()]

        # Chuyển đổi thành key: value
        flattened_data = {key: list(value.values())[0] for key, value in data.items()}

        print(flattened_data)

        # strengths, weakness = rag.identify_strengths_weaknesses(flattened_data)

        # print(strengths, weakness)

        # prompt = rag.create_prompt_predict_score(flattened_data, final_grade, strengths, weakness)
        prompt = rag.create_prompt_learning_analyze(flattened_data,final_grade, courses_period,subject_weakens_array)

        response = call_llm_query("get solution for student", prompt)
        answer = response.text
        clean_answer = re.sub(r"^```json\s*|```$", "", answer.strip())
        print(clean_answer)
        data = json.loads(clean_answer)
        data["subject_weakens"] = subject_weakens_array

        return jsonify(
            {
                "code": 200,
                "message": "success",
                "data": data
            }
        )
    except Error as e:
        abort(400, "Error when providing solutions for students.")

@app.route(f"{BASE_URL}/document/generate-question", methods=['GET'])
def handle_generate_question():
    try:
        doc_ids = request.args.get("docIds")
        if doc_ids:
            doc_ids_list = doc_ids.split(",")
            doc_ids_list = [int(doc_id) for doc_id in doc_ids_list]
        else:
            return {"error": "No docIds provided"}, 400
        documents = query_db.get_document_by_id(doc_ids_list)
        full_text = "".join([doc["content"] for doc in documents])
        words= ReadFile.clean_and_tokenize(ReadFile(),full_text)
        max_chunk_size = 4000
        responses= []
        list_question= []
        if len(words) > max_chunk_size:
            word_chunks = [words[i:i + max_chunk_size] for i in range(0, len(words), max_chunk_size)]
        else:
            word_chunks = [words]

        for i,word in enumerate(word_chunks):
            print(f"🔹Get question {i+1}/{len(word_chunks)}...")
            get_prompt = rag.create_prompt_get_question(word)
            response= call_llm_query("Take multiple choice questions from the document",get_prompt)
            responses.append(response.text)

        for response in responses:
            questions= ReadFile.extract_questions_and_answers(response)
            list_question= list_question + questions

        return ApiResponse.success(data=list_question)
    except Exception as e:
        return ApiResponse.error(message=f"An unexpected error occurred: {str(e)}", code=500)


@app.route(f"{BASE_URL}/document/generate-assignment", methods=['GET'])
def handle_generate_assignment():
    try:
        doc_id = int(request.args.get("docId"))
        number_question = int(request.args.get("numberQuestion"))

        if not doc_id or not number_question:
            ApiResponse.error(message=f"No request provided", code=400)

        documents = query_db.get_document_by_id(doc_id)
        full_text = "".join([doc["content"] for doc in documents])
        words= ReadFile.clean_and_tokenize(ReadFile(),full_text)
        max_chunk_size = 10000
        responses= []
        list_question= []
        if len(words) > max_chunk_size:
            word_chunks = [words[i:i + max_chunk_size] for i in range(0, len(words), max_chunk_size)]
        else:
            word_chunks = [words]

        for i,word in enumerate(word_chunks):
            print(f"🔹Get question {i+1}/{len(word_chunks)}...")
            get_prompt = rag.create_prompt_get_question(word,number_question)
            response= call_llm_query("Take multiple choice questions from the document",get_prompt)
            responses.append(response.text)

        for response in responses:
            questions= ReadFile.extract_questions_and_answers(response)
            list_question= list_question + questions

        return ApiResponse.success(data=list_question)
    except Exception as e:
        return ApiResponse.error(message=f"An unexpected error occurred: {str(e)}", code=500)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002, debug=True)

