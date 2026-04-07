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
DB_NAME = "ecommerce.db"

# Mount static directory for frontend
# We will create 'static' folder later
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

class QueryRequest(BaseModel):
    query: str

class QueryResponse(BaseModel):
    sql_query: str
    results: list
    columns: list
    message: str = ""

def get_db_schema():
    """Retrieve database schema to provide context to the LLM."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    conn.close()
    
    schema = []
    for table_name, table_sql in tables:
        if table_name != "sqlite_sequence":
            schema.append(f"Table '{table_name}':\n{table_sql}")
    
    return "\n\n".join(schema)

def execute_sql(sql_query: str):
    """Safely execute a read-only SQL query."""
    if not sql_query.lower().strip().startswith("select"):
        raise ValueError("Only SELECT queries are permitted.")
        
    conn = sqlite3.connect(DB_NAME)
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

@app.post("/api/query", response_model=QueryResponse)
def handle_query(req: QueryRequest):
    if not openai.api_key or openai.api_key == 'your_openai_api_key_here':
        raise HTTPException(
            status_code=500, 
            detail="OpenAI API Key is missing. Please add it to your .env file."
        )

    user_query = req.query
    schema = get_db_schema()

    prompt = f"""
You are an expert SQL assistant. I will provide you with a database schema and a question in natural language.
Your task is to respond ONLY with the raw SQL query to answer the question. Do not include markdown formatting (like ```sql), do not include explanations, just the SQL query itself.
It must be a valid SQLite query. It must only be a SELECT statement.

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
        
        # Remove markdown if the model included it despite instructions
        if sql_query.startswith("```"):
            sql_query = sql_query.split("\n", 1)[1]
            if sql_query.endswith("```"):
                sql_query = sql_query.rsplit("\n", 1)[0]
        sql_query = sql_query.strip()
        
        if not sql_query.endswith(";"):
            sql_query += ";"

        columns, results = execute_sql(sql_query)
        
        return QueryResponse(
            sql_query=sql_query,
            columns=columns,
            results=results,
            message="Query executed successfully."
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
