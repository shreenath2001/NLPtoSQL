import os
import sqlite3
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv
import openai
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime
import re
from cryptography.fernet import Fernet

# Load environment variables
load_dotenv()

# Configure OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

# Initialize FastAPI app
app = FastAPI()

# Base Directory for absolute paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Database config
DB_DIR = os.path.join(BASE_DIR, "databases")
os.makedirs(DB_DIR, exist_ok=True)

# Registry Configuration (Absolute Path)
REGISTRY_DB = os.path.join(DB_DIR, "registry.sqlite")
REGISTRY_URL = f"sqlite:///{REGISTRY_DB}"
registry_engine = create_engine(REGISTRY_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=registry_engine)
Base = declarative_base()

# Encryption Configuration
class Cipher:
    """Utility for encrypting and decrypting sensitive data."""
    def __init__(self):
        self.key = os.getenv("DB_ENCRYPTION_KEY")
        if not self.key:
            self.key = Fernet.generate_key().decode()
            self._save_key_to_env(self.key)
        self.fernet = Fernet(self.key.encode())

    def _save_key_to_env(self, key: str):
        env_path = os.path.join(BASE_DIR, ".env")
        with open(env_path, "a") as f:
            f.write(f"\nDB_ENCRYPTION_KEY={key}\n")
        print("Generated new DB_ENCRYPTION_KEY and saved to .env")

    def encrypt(self, data: str) -> str:
        if not data: return data
        return self.fernet.encrypt(data.encode()).decode()

    def decrypt(self, token: str) -> str:
        if not token: return token
        try:
            return self.fernet.decrypt(token.encode()).decode()
        except Exception:
            # If decryption fails, assume it's already plain text (for migration)
            return token

cipher = Cipher()

class RegisteredSchema(Base):
    __tablename__ = "schemas"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    connection_url = Column(String, nullable=False)
    type = Column(String, nullable=False) # 'local' or 'remote'
    created_at = Column(DateTime, default=datetime.utcnow)

def init_registry():
    Base.metadata.create_all(bind=registry_engine)
    
    # Migrate existing .db files if any
    session = SessionLocal()
    try:
        # 1. Migrate local files to registry
        if os.path.exists(DB_DIR):
            for f in os.listdir(DB_DIR):
                if f.endswith(".db") and f != "registry.sqlite":
                    name = f[:-3]
                    existing = session.query(RegisteredSchema).filter_by(name=name).first()
                    if not existing:
                        abs_path = os.path.abspath(os.path.join(DB_DIR, f))
                        new_schema = RegisteredSchema(
                            name=name,
                            connection_url=cipher.encrypt(f"sqlite:///{abs_path}"),
                            type="local"
                        )
                        session.add(new_schema)
                        print(f"Migrated local schema to registry: {name}")
        
        # 2. Migrate existing plaintext URLs to encrypted ones
        all_schemas = session.query(RegisteredSchema).all()
        for idx, s in enumerate(all_schemas):
            # If the URL doesn't look like an encrypted Fernet token (usually starts with gAAAA)
            # we encrypt it.
            if not s.connection_url.startswith("gAAAA"):
                print(f"Encrypting legacy credentials for: {s.name}")
                s.connection_url = cipher.encrypt(s.connection_url)
        
        session.commit()
    finally:
        session.close()

# Initialize registry on startup
init_registry()

# Mount static directory for frontend
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

class QueryRequest(BaseModel):
    query: str
    schema_name: str = "ecommerce"

class SchemaCreateRequest(BaseModel):
    name: str
    sql_script: str = ""
    connection_url: str = ""

class QueryResponse(BaseModel):
    sql_query: str = ""
    results: list = []
    columns: list = []
    message: str = ""
    analysis: str = ""
    chat_response: str = ""

import re

def is_valid_custom_schema_script(script: str) -> bool:
    # Remove single-line and multi-line comments before passing validation
    script_clean = re.sub(r'--.*', '', script)
    script_clean = re.sub(r'/\*.*?\*/', '', script_clean, flags=re.DOTALL)
    
    statements = [stmt.strip() for stmt in script_clean.split(';') if stmt.strip()]
    if not statements:
        return False
    
    forbidden_keywords = [
        r'\bDROP\b', r'\bDELETE\b', r'\bUPDATE\b', r'\bALTER\b', 
        r'\bPRAGMA\b', r'\bATTACH\b', r'\bDETACH\b', r'\bEXPLAIN\b', 
        r'\bVACUUM\b', r'\bREPLACE\b'
    ]
    
    for stmt in statements:
        upper_stmt = stmt.upper()
        if not (upper_stmt.startswith("CREATE") or upper_stmt.startswith("INSERT")):
            return False
            
        # Create a copy for checking that ignores valid constraint phrases
        stmt_to_check = re.sub(r'\bON\s+DELETE\b', 'ON_DEL_PLACEHOLDER', stmt, flags=re.IGNORECASE)
        stmt_to_check = re.sub(r'\bON\s+UPDATE\b', 'ON_UPD_PLACEHOLDER', stmt_to_check, flags=re.IGNORECASE)

        for forbidden in forbidden_keywords:
            if re.search(forbidden, stmt_to_check, re.IGNORECASE):
                return False
    return True

def normalize_connection_url(url: str) -> str:
    """Automatically inject required drivers for common databases."""
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    if url.startswith("mysql://"):
        return url.replace("mysql://", "mysql+pymysql://", 1)
    return url

def get_engine_for_schema(schema_name: str):
    """Universal connector that handles decryption, driver normalization, and stability flags."""
    session = SessionLocal()
    try:
        registered = session.query(RegisteredSchema).filter_by(name=schema_name).first()
        if not registered:
            raise ValueError(f"Schema '{schema_name}' does not exist.")
        
        # Decrypt URL before use
        raw_url = cipher.decrypt(registered.connection_url)
        url = normalize_connection_url(raw_url)
        
        connect_args = {}
        if url.startswith("sqlite"):
            connect_args = {"check_same_thread": False}
            
        return create_engine(url, connect_args=connect_args, pool_pre_ping=True)
    finally:
        session.close()

def get_db_schema(schema_name: str):
    """Retrieve database schema for LLM context using the universal connector."""
    try:
        engine = get_engine_for_schema(schema_name)
    except ValueError as e:
        raise e
        
    inspector = inspect(engine)
    schema = []
    try:
        for table_name in inspector.get_table_names():
            if table_name == "sqlite_sequence": continue
            columns = inspector.get_columns(table_name)
            col_strings = [f"{col['name']} ({col['type']})" for col in columns]
            schema.append(f"Table '{table_name}':\nColumns: {', '.join(col_strings)}")
    except Exception as e:
        raise ValueError(f"Error inspecting database: {str(e)}")
    
    return "\n\n".join(schema)

def execute_sql(sql_query: str, schema_name: str):
    """Safely execute a read-only SQL query using the universal connector."""
    if not sql_query.lower().strip().startswith("select"):
        raise ValueError("Only SELECT queries are permitted.")
        
    try:
        engine = get_engine_for_schema(schema_name)
        with engine.connect() as connection:
            result = connection.execute(text(sql_query))
            columns = list(result.keys())
            rows = [list(row) for row in result.fetchall()]
            return columns, rows
    except Exception as e:
        raise ValueError(f"Database error: {str(e)}")

@app.get("/")
def read_root():
    """Serve the main frontend page."""
    return FileResponse("static/index.html")

@app.get("/api/schemas")
def list_schemas():
    session = SessionLocal()
    try:
        registered = session.query(RegisteredSchema).all()
        return {"schemas": [s.name for s in registered]}
    finally:
        session.close()

@app.post("/api/schemas")
def create_schema(req: SchemaCreateRequest):
    if not re.match(r'^[a-zA-Z0-9_]+$', req.name):
        raise HTTPException(status_code=400, detail="Invalid schema name. Use alphanumeric characters and underscores only.")
        
    session = SessionLocal()
    try:
        existing = session.query(RegisteredSchema).filter_by(name=req.name).first()
        if existing:
            raise HTTPException(status_code=400, detail=f"Schema '{req.name}' already exists.")

        if req.connection_url:
            normalized_url = normalize_connection_url(req.connection_url)
            
            # Verify connection before saving
            try:
                test_connect_args = {}
                if normalized_url.startswith("sqlite"):
                    test_connect_args = {"check_same_thread": False}
                test_engine = create_engine(normalized_url, connect_args=test_connect_args)
                with test_engine.connect() as conn:
                    pass
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Could not connect to database with provided URL: {str(e)}")
                
            new_schema = RegisteredSchema(
                name=req.name,
                connection_url=cipher.encrypt(req.connection_url),
                type="remote"
            )
            session.add(new_schema)
            session.commit()
            return {"message": f"Remote schema '{req.name}' registered successfully (encrypted)."}
            
        elif req.sql_script:
            if not is_valid_custom_schema_script(req.sql_script):
                raise HTTPException(status_code=400, detail="Invalid SQL script. Only CREATE and INSERT statements are allowed.")
                
            db_path = os.path.join(DB_DIR, f"{req.name}.db")
            if os.path.exists(db_path):
                raise HTTPException(status_code=400, detail=f"Schema file '{req.name}.db' already exists.")
                
            conn = sqlite3.connect(db_path)
            try:
                conn.executescript(req.sql_script)
                conn.commit()
            except Exception as e:
                conn.close()
                if os.path.exists(db_path): os.remove(db_path)
                raise HTTPException(status_code=400, detail=f"Error executing schema script: {str(e)}")
            finally:
                conn.close()

            new_schema = RegisteredSchema(
                name=req.name,
                connection_url=cipher.encrypt(f"sqlite:///{os.path.abspath(db_path)}"),
                type="local"
            )
            session.add(new_schema)
            session.commit()
            return {"message": f"Local schema '{req.name}' created and registered successfully (encrypted)."}
        else:
            raise HTTPException(status_code=400, detail="Either 'sql_script' or 'connection_url' must be provided.")
    finally:
        session.close()

@app.get("/api/schema/{name}")
def get_schema_info_api(name: str):
    """Retrieve schema info API using the universal connector with robust error handling."""
    try:
        engine = get_engine_for_schema(name)
        inspector = inspect(engine)
        
        schema_info = []
        tables = inspector.get_table_names()
        for table_name in tables:
            if table_name == "sqlite_sequence": continue
            
            columns = inspector.get_columns(table_name)
            col_info = []
            for col in columns:
                # Basic PK and type detection
                type_badge = str(col['type']).split('(')[0].upper()[:4]
                if col.get('primary_key'): type_badge = "PK"
                col_info.append({"name": col['name'], "type": type_badge})
                
            schema_info.append({"name": table_name, "columns": col_info})
        return {"tables": schema_info}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        # Prevent 500 error by returning a descriptive 400 error
        raise HTTPException(status_code=400, detail=f"Connection Error: {str(e)}")

@app.post("/api/query", response_model=QueryResponse)
def handle_query(req: QueryRequest):
    if not openai.api_key or openai.api_key == 'your_openai_api_key_here':
        raise HTTPException(
            status_code=500, 
            detail="OpenAI API Key is missing. Please add it to your .env file."
        )

    user_query = req.query
    schema_name = req.schema_name
    
    try:
        schema = get_db_schema(schema_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    prompt = f"""
You are an expert SQL assistant. I will provide you with a database schema and a question in natural language.
If the question can be answered using the provided schema, respond ONLY with the raw SQL query to answer the question. Do not include markdown formatting (like ```sql), do not include explanations, just the SQL query itself. It must be a valid SQLite query and must only be a SELECT statement.

If the question is unrelated to the database, or if it is impossible to generate a meaningful SQL query based on the schema, reply EXACTLY with a conversational response starting with 'CHAT_RESPONSE: '. Explain politely that you can only answer questions related to the current database, and guide them to ask about the available data.

### Schema:
{schema}

### Question:
{user_query}
"""

    try:
        # Call OpenAI API
        client = openai.OpenAI()
        response = client.chat.completions.create(
            model="gpt-3.5-turbo", # We will use 3.5-turbo by default as it's faster and cheaper, or 4o if desired. 
            messages=[
                {"role": "system", "content": "You are a helpful database assistant that writes SQL queries."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.0
        )
        
        sql_query = response.choices[0].message.content.strip()
        
        if sql_query.startswith("CHAT_RESPONSE:"):
            return QueryResponse(
                chat_response=sql_query.replace("CHAT_RESPONSE:", "").strip()
            )
            
        # Remove markdown if the model included it despite instructions
        if sql_query.startswith("```"):
            sql_query = sql_query.split("\n", 1)[1]
            if sql_query.endswith("```"):
                sql_query = sql_query.rsplit("\n", 1)[0]
        sql_query = sql_query.strip()
        
        if not sql_query.endswith(";"):
            sql_query += ";"

        columns, results = execute_sql(sql_query, schema_name)
        
        analysis = ""
        if results:
            limited_results = results[:50]
            analysis_prompt = f"""
You are an expert data analyst. Based on the following user question, SQL query, and gathered results, provide a concise and insightful analysis or summary of the findings. Maintain a helpful and professional tone.

### User Question:
{user_query}

### SQL Query:
{sql_query}

### Results (up to 50 rows):
Columns: {columns}
Rows: {limited_results}
"""
            try:
                analysis_response = client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "You are a helpful data analyst."},
                        {"role": "user", "content": analysis_prompt}
                    ],
                    temperature=0.5
                )
                analysis = analysis_response.choices[0].message.content.strip()
            except Exception as e:
                print(f"Analysis generation failed: {e}")
                analysis = ""

        return QueryResponse(
            sql_query=sql_query,
            columns=columns,
            results=results,
            message="Query executed successfully.",
            analysis=analysis
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
