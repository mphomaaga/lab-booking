from fastapi import FastAPI

app = FastAPI(title="Lab booking")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
