from fastapi import FastAPI

app = FastAPI(title="IntegraHub", version="0.1.0")


@app.get("/api/v1/customers/{customer_id}/profile")
async def profile(customer_id: int):
    return {"customerId": customer_id, "customer": None, "products": [],
            "partial": True, "warnings": [{"provider": "CORE", "code": "SKELETON",
            "message": "Esqueleto inicial; integración pendiente."}]}
