import os
import json
import sqlite3
import hashlib
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer

DB_PATH = os.path.join(os.path.dirname(__file__), 'edugenie_users.db')

def init_db():
    con = sqlite3.connect(DB_PATH)
    con.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            academic_level TEXT NOT NULL
        )
    ''')
    con.commit()
    con.close()

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def generate_educational_content(prompt, schema=None):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise Exception("GEMINI_API_KEY environment variable is missing.")
    
    models_to_try = ["gemini-2.5-flash", "gemini-1.5-flash", "gemini-1.5-pro"]
    last_error = None

    for model_name in models_to_try:
        for attempt in range(1, 3):
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
            
            payload = {
                "contents": [{
                    "parts": [{
                        "text": prompt
                    }]
                }]
            }
            
            if schema:
                payload["generationConfig"] = {
                    "responseMimeType": "application/json",
                    "responseSchema": schema,
                    "temperature": 0.7
                }
            else:
                payload["generationConfig"] = {
                    "temperature": 0.7
                }
                
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "aistudio-build"
                }
            )
            
            try:
                with urllib.request.urlopen(req) as response:
                    res_body = response.read().decode("utf-8")
                    res_json = json.loads(res_body)
                    candidates = res_json.get("candidates", [])
                    if candidates:
                        text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                        if text:
                            return text
            except Exception as e:
                last_error = e
                print(f"[EduGenie AI Warning] Model {model_name} (attempt {attempt}/2) failed: {e}")
                if attempt < 2:
                    import time
                    time.sleep(0.6)
                    
    print("All Gemini API models and fallback retries were exhausted.", last_error)
    raise Exception(f"All Gemini API models were temporarily unavailable: {last_error}")


class APIRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Override to suppress standard console spam, or print custom format
        print(f"[Python API Server] {format % args}")

    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_POST(self):
        allowed = ["/api/qa", "/api/explain", "/api/quiz", "/api/summarize",
                   "/api/learning-path", "/api/auth/register", "/api/auth/login"]
        if self.path not in allowed:
            self.send_response(404)
            self.send_header('Content-Type', 'application/json')
            self._cors()
            self.end_headers()
            self.wfile.write(b'{"error": "Not Found"}')
            return

        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)

        try:
            req_body = json.loads(post_data.decode('utf-8')) if post_data else {}
        except Exception:
            self.send_response(400)
            self.send_header('Content-Type', 'application/json')
            self._cors()
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Invalid JSON body"}).encode('utf-8'))
            return

        try:
            res_data = None
            if self.path == "/api/auth/register":
                res_data = self.handle_register(req_body)
            elif self.path == "/api/auth/login":
                res_data = self.handle_login(req_body)
            elif self.path == "/api/qa":
                res_data = self.handle_qa(req_body)
            elif self.path == "/api/explain":
                res_data = self.handle_explain(req_body)
            elif self.path == "/api/quiz":
                res_data = self.handle_quiz(req_body)
            elif self.path == "/api/summarize":
                res_data = self.handle_summarize(req_body)
            elif self.path == "/api/learning-path":
                res_data = self.handle_learning_path(req_body)

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self._cors()
            self.end_headers()
            self.wfile.write(json.dumps(res_data).encode('utf-8'))
        except Exception as e:
            print(f"[Python API Error] Path {self.path} failed: {e}")
            msg = str(e)
            status = 409 if "already exists" in msg else 401 if "Invalid" in msg else 500
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self._cors()
            self.end_headers()
            self.wfile.write(json.dumps({"error": msg}).encode('utf-8'))

    def handle_register(self, body):
        name = body.get('name', '').strip()
        email = body.get('email', '').strip().lower()
        password = body.get('password', '')
        academic_level = body.get('academicLevel', 'Lifelong Learner')
        if not name or not email or not password:
            raise Exception('Name, email, and password are required.')
        con = sqlite3.connect(DB_PATH)
        try:
            con.execute(
                'INSERT INTO users (name, email, password_hash, academic_level) VALUES (?, ?, ?, ?)',
                (name, email, hash_password(password), academic_level)
            )
            con.commit()
        except sqlite3.IntegrityError:
            raise Exception('An account with this email already exists.')
        finally:
            con.close()
        return {'name': name, 'email': email, 'academicLevel': academic_level}

    def handle_login(self, body):
        email = body.get('email', '').strip().lower()
        password = body.get('password', '')
        if not email or not password:
            raise Exception('Email and password are required.')
        con = sqlite3.connect(DB_PATH)
        row = con.execute(
            'SELECT name, email, academic_level FROM users WHERE email = ? AND password_hash = ?',
            (email, hash_password(password))
        ).fetchone()
        con.close()
        if not row:
            raise Exception('Invalid email or password combination.')
        return {'name': row[0], 'email': row[1], 'academicLevel': row[2]}

    def handle_qa(self, body):
        question = body.get("question")
        grade_level = body.get("gradeLevel", "General")
        subject = body.get("subject", "General Science")
        
        if not question:
            raise Exception("Question is required.")
            
        prompt = f"""You are EduGenie, an expert educational tutor.
The student is asking a question about the subject "{subject}" at a "{grade_level}" level.
Question: "{question}"

Provide an educational response in JSON format. Do not use generic answers; give accurate facts and context.
The response MUST adhere to this exact JSON schema:
{{
  "answer": "string (Comprehensive, clear educational answer. Use markdown for lists or equations if helpful. Explain the concepts clearly)",
  "keyTerms": ["array of 2-4 important vocabulary words mentioned in the explanation"],
  "followUpQuestions": ["array of 2-3 engaging questions for the student to explore next"],
  "funFact": "string (An interesting, context-relevant fun educational fact to spark interest)"
}}"""

        schema = {
            "type": "OBJECT",
            "properties": {
                "answer": { "type": "STRING", "description": "Detailed, structured response with beautiful markdown" },
                "keyTerms": {
                    "type": "ARRAY",
                    "items": { "type": "STRING" },
                    "description": "Key terminology and vocabulary"
                },
                "followUpQuestions": {
                    "type": "ARRAY",
                    "items": { "type": "STRING" },
                    "description": "Follow-up exploration questions"
                },
                "funFact": { "type": "STRING", "description": "Exciting context-relevant fun fact" }
            },
            "required": ["answer", "keyTerms", "followUpQuestions", "funFact"]
        }
        
        res_text = generate_educational_content(prompt, schema)
        return json.loads(res_text)

    def handle_explain(self, body):
        concept = body.get("concept")
        depth = body.get("depth", "teenager")
        
        if not concept:
            raise Exception("Concept name is required.")
            
        depth_descriptions = {
            "child": "a 5-year old child. Use very simple language, playful tone, and magical analogies.",
            "teenager": "a high schooler (14-16 years old). Use engaging, trendy yet clear explanations and friendly analogies.",
            "undergrad": "a college undergraduate. Use academic terminology, precise definitions, and comprehensive conceptual frameworks.",
            "expert": "a seasoned professional. Use advanced terminology, current field practices, mathematical or logical precision."
        }
        
        current_depth_text = depth_descriptions.get(depth, depth_descriptions["teenager"])
        
        prompt = f"""You are EduGenie, an elite educator specialized in explaining complex topics simply.
Please explain the concept "{concept}" for an audience at the level of: {current_depth_text}

The response MUST adhere to this exact JSON schema:
{{
  "conceptName": "string (The concept title)",
  "analogy": "string (A highly relatable real-world comparison suitable for the target audience)",
  "coreExplanation": "string (Clear, well-structured explanation using markdown. Maintain appropriate academic depth according to the audience)",
  "threeKeyTakeaways": ["takeaway 1", "takeaway 2", "takeaway 3"],
  "commonMisconception": "string (A common mistake or misconception about this concept and why it is wrong)"
}}"""

        schema = {
            "type": "OBJECT",
            "properties": {
                "conceptName": { "type": "STRING" },
                "analogy": { "type": "STRING", "description": "Rich, relatable comparison or metaphor" },
                "coreExplanation": { "type": "STRING", "description": "Detailed multi-paragraph markdown text" },
                "threeKeyTakeaways": {
                    "type": "ARRAY",
                    "items": { "type": "STRING" },
                    "description": "Exactly three critical bullet points"
                },
                "commonMisconception": { "type": "STRING", "description": "Clarification on a popular myth/error" }
            },
            "required": ["conceptName", "analogy", "coreExplanation", "threeKeyTakeaways", "commonMisconception"]
        }
        
        res_text = generate_educational_content(prompt, schema)
        return json.loads(res_text)

    def handle_quiz(self, body):
        topic = body.get("topic")
        num_questions = body.get("numQuestions", 5)
        quiz_type = body.get("quizType", "multiple_choice")
        
        if not topic:
            raise Exception("Topic is required.")
            
        type_desc = "True or False questions" if quiz_type == "true_false" else "Multiple Choice questions (with exactly 4 options)"
        
        prompt = f"""You are EduGenie, an educational psychometrician.
Generate a high-quality educational quiz on the topic "{topic}".
Generate exactly {num_questions} questions of type: {type_desc}.

Ensure questions test conceptual understanding, not just surface-level memorization.
The response MUST adhere to this exact JSON schema:
{{
  "topic": "string",
  "questions": [
    {{
      "id": 1,
      "text": "string (The question text)",
      "options": ["Option A", "Option B", "Option C", "Option D"],
      "correctAnswer": "string (Must match exactly one of the options above. For true/false, the options must be ['True', 'False'] and correct must be 'True' or 'False')",
      "explanation": "string (Comprehensive explanation of why the correct option is correct and why other distractors are wrong)"
    }}
  ]
}}"""

        schema = {
            "type": "OBJECT",
            "properties": {
                "topic": { "type": "STRING" },
                "questions": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "id": { "type": "INTEGER" },
                            "text": { "type": "STRING" },
                            "options": {
                                "type": "ARRAY",
                                "items": { "type": "STRING" }
                            },
                            "correctAnswer": { "type": "STRING" },
                            "explanation": { "type": "STRING" }
                        },
                        "required": ["id", "text", "options", "correctAnswer", "explanation"]
                    }
                }
            },
            "required": ["topic", "questions"]
        }
        
        res_text = generate_educational_content(prompt, schema)
        return json.loads(res_text)

    def handle_summarize(self, body):
        text = body.get("text")
        format_val = body.get("format", "bullets")
        
        if not text or len(text.strip()) < 10:
            raise Exception("Please enter a valid longer educational text.")
            
        prompt = f"""You are EduGenie, an educational researcher.
Summarize the following educational content:
"{text}"

Format your response specifically for learning. Support the format request: "{format_val}".
Provide your final output adhering to this JSON schema:
{{
  "title": "string (A creative, educational title for the summarized material)",
  "summary": "string (A clear, concise summary of the material. For 'bullets' format, make it brief. For 'comprehensive', make it descriptive using markdown subheadings)",
  "keyTakeaways": ["3-5 array of key learning points / insights"],
  "flashcards": [
    {{
      "front": "string (A key concept, question, or term)",
      "back": "string (The corresponding definition, answer, or explanation)"
    }}
  ]
}}"""

        schema = {
            "type": "OBJECT",
            "properties": {
                "title": { "type": "STRING" },
                "summary": { "type": "STRING" },
                "keyTakeaways": {
                    "type": "ARRAY",
                    "items": { "type": "STRING" }
                },
                "flashcards": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "front": { "type": "STRING" },
                            "back": { "type": "STRING" }
                        },
                        "required": ["front", "back"]
                    }
                }
            },
            "required": ["title", "summary", "keyTakeaways", "flashcards"]
        }
        
        res_text = generate_educational_content(prompt, schema)
        return json.loads(res_text)

    def handle_learning_path(self, body):
        topic = body.get("topic")
        experience_level = body.get("experienceLevel", "beginner")
        
        if not topic:
            raise Exception("Topic is required.")
            
        prompt = f"""You are EduGenie, an academic advisor and instructional designer.
Create a structured, personalized learning path for studying the topic "{topic}" starting at a "{experience_level}" level.

The output MUST be highly actionable, detailed, and guide the student from their starting point to higher skill levels.
The response MUST adhere to this exact JSON schema:
{{
  "topic": "string",
  "overview": "string (A friendly, motivating overview of what they will learn and why it matters)",
  "estimatedTime": "string (e.g., '6 Weeks (5 hours/week)')",
  "milestones": [
    {{
      "level": "string (e.g. Phase 1: Foundations, Phase 2: Core Concepts, Phase 3: Advanced Practical Applications)",
      "title": "string (Topic/Objective of this milestone)",
      "topics": ["array of specific sub-topics to master"],
      "learningObjective": "string (What the learner will be able to do by the end of this phase)",
      "suggestedProjects": ["array of 1-2 hands-on, realistic practice projects or activities"],
      "recommendedResources": ["array of 2-3 specific study suggestions, exercise ideas, or resources"]
    }}
  ],
  "progressionCriteria": "string (A self-assessment checklist or description of how the student knows they are ready to move on to the next major subject)"
}}"""

        schema = {
            "type": "OBJECT",
            "properties": {
                "topic": { "type": "STRING" },
                "overview": { "type": "STRING" },
                "estimatedTime": { "type": "STRING" },
                "milestones": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "level": { "type": "STRING" },
                            "title": { "type": "STRING" },
                            "topics": {
                                "type": "ARRAY",
                                "items": { "type": "STRING" }
                            },
                            "learningObjective": { "type": "STRING" },
                            "suggestedProjects": {
                                "type": "ARRAY",
                                "items": { "type": "STRING" }
                            },
                            "recommendedResources": {
                                "type": "ARRAY",
                                "items": { "type": "STRING" }
                            }
                        },
                        "required": ["level", "title", "topics", "learningObjective", "suggestedProjects", "recommendedResources"]
                    }
                },
                "progressionCriteria": { "type": "STRING" }
            },
            "required": ["topic", "overview", "estimatedTime", "milestones", "progressionCriteria"]
        }
        
        res_text = generate_educational_content(prompt, schema)
        return json.loads(res_text)

def run_server():
    init_db()
    port = 5000
    server_address = ('127.0.0.1', port)
    httpd = HTTPServer(server_address, APIRequestHandler)
    print(f"[Python API Server] Running on http://127.0.0.1:{port}...")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("[Python API Server] Shutting down...")
        httpd.server_close()

if __name__ == "__main__":
    run_server()
