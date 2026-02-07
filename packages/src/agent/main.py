from fastapi import FastAPI, HTTPException
from agent_main import AgentExecutor
import uvicorn

app = FastAPI()

@app.post("/agent/{user_id}")
async def agent_endpoint(user_id: int, body: dict):
    try:
        msg = body.get("msg")
        if not msg:
            raise ValueError("Missing 'msg' field in request body")
        
        response = AgentExecutor().invoke(msg)
        return {"response": response}
    except Exception as e:
        print(f"Error in Agent Endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))
        
    
        
        
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8002)