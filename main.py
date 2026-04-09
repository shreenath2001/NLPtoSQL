import os
import sqlite3
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv
import openai

# Load environment variables
load_dotenv()

# Configure OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

# Initialize FastAPI app
app = FastAPI()

# Database config
DB_DIR = "databases"
os.makedirs(DB_DIR, exist_ok=True)

# Mount static directory for frontend
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

class QueryRequest(BaseModel):
    query: str
    schema_name: str = "ecommerce"

class SchemaCreateRequest(BaseModel):
    name: str
    sql_script: str

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
            
        for forbidden in forbidden_keywords:
            if re.search(forbidden, stmt, re.IGNORECASE):
                return False
    return True

def get_db_schema(schema_name: str):
    """Retrieve database schema to provide context to the LLM."""
    db_path = os.path.join(DB_DIR, f"{schema_name}.db")
    if not os.path.exists(db_path):
        raise ValueError(f"Schema '{schema_name}' does not exist.")
        
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    conn.close()
    
    schema = []
    for table_name, table_sql in tables:
        if table_name != "sqlite_sequence":
            schema.append(f"Table '{table_name}':\n{table_sql}")
    
    return "\n\n".join(schema)

def execute_sql(sql_query: str, schema_name: str):
    """Safely execute a read-only SQL query."""
    if not sql_query.lower().strip().startswith("select"):
        raise ValueError("Only SELECT queries are permitted.")
        
    db_path = os.path.join(DB_DIR, f"{schema_name}.db")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute(sql_query)
        columns = [description[0] for description in cursor.description]
        results = cursor.fetchall()
        return columns, results
    finally:
        conn.close()

@app.get("/")
def read_root():
    """Serve the main frontend page."""
    return FileResponse("static/index.html")

@app.get("/api/schemas")
def list_schemas():
    schemas = []
    for f in os.listdir(DB_DIR):
        if f.endswith(".db"):
            schemas.append(f[:-3])
    return {"schemas": schemas}

@app.post("/api/schemas")
def create_schema(req: SchemaCreateRequest):
    if not re.match(r'^[a-zA-Z0-9_]+$', req.name):
        raise HTTPException(status_code=400, detail="Invalid schema name. Use alphanumeric characters and underscores only.")
        
    if not is_valid_custom_schema_script(req.sql_script):
        raise HTTPException(status_code=400, detail="Invalid SQL script. Only CREATE and INSERT statements are allowed. Destructive commands (DROP, DELETE, etc.) are strictly prohibited.")
        
    db_path = os.path.join(DB_DIR, f"{req.name}.db")
    if os.path.exists(db_path):
        raise HTTPException(status_code=400, detail=f"Schema '{req.name}' already exists.")
        
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.executescript(req.sql_script)
        conn.commit()
        return {"message": f"Schema '{req.name}' created successfully."}
    except Exception as e:
        if conn:
            conn.close()
            conn = None
        if os.path.exists(db_path):
            os.remove(db_path)
        raise HTTPException(status_code=400, detail=f"Error executing schema script: {str(e)}")
    finally:
        if conn:
            conn.close()

@app.get("/api/schema/{name}")
def get_schema_info(name: str):
    db_path = os.path.join(DB_DIR, f"{name}.db")
    if not os.path.exists(db_path):
        raise HTTPException(status_code=404, detail="Schema not found")
        
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    
    schema_info = []
    for (table_name,) in tables:
        if table_name == "sqlite_sequence":
            continue
        cursor.execute(f"PRAGMA table_info({table_name});")
        columns = cursor.fetchall()
        
        col_info = []
        for col in columns:
            cid, col_name, col_type, notnull, dflt_value, pk = col
            if pk:
                type_badge = "PK"
            else:
                type_badge = col_type.split()[0].upper()[:4] if col_type else "STR"
            col_info.append({"name": col_name, "type": type_badge})
            
        schema_info.append({"name": table_name, "columns": col_info})
        
    conn.close()
    return {"tables": schema_info}

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
