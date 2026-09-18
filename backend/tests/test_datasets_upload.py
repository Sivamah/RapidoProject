import pytest
import io
from fastapi.testclient import TestClient
from app.main import app
from app.api.deps import get_current_user
from app.db.database import SessionLocal
from app.db.models import User, Vehicle, Provider

def override_get_current_user():
    return User(id=1, email="test@test.com", role="Admin")

app.dependency_overrides[get_current_user] = override_get_current_user

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c

def test_dataset_upload_imports_vehicles(client):
    db = SessionLocal()
    # Ensure no lingering CBE-V vehicles from this test
    db.query(Vehicle).filter(Vehicle.name.like("CBE-V-90%")).delete(synchronize_session=False)
    db.commit()
    
    csv_content = """vehicle_id,vehicle_type,capacity,status,latitude,longitude,fuel_type
CBE-V-901,Car,4,Available,11.0132,76.9558,Petrol
CBE-V-902,Van,8,Busy,11.0216,76.9701,Diesel
"""
    files = {'file': ('test_vehicles.csv', io.BytesIO(csv_content.encode("utf-8")), 'text/csv')}
    data = {'name': 'test_vehicles', 'file_type': 'csv', 'data_type': 'vehicle', 'description': 'Test vehicle import'}
    
    response = client.post('/api/orchestration/datasets/upload', files=files, data=data)
    assert response.status_code == 200
    
    # Verify DB
    vehicles = db.query(Vehicle).filter(Vehicle.name.in_(["CBE-V-901", "CBE-V-902"])).all()
    assert len(vehicles) == 2
    
    v1 = next((v for v in vehicles if v.name == "CBE-V-901"), None)
    v2 = next((v for v in vehicles if v.name == "CBE-V-902"), None)
    
    assert v1 is not None
    assert v1.capacity == 4
    assert v1.status == "Available"
    
    assert v2 is not None
    assert v2.capacity == 8
    assert v2.status == "Busy"
    
    db.query(Vehicle).filter(Vehicle.name.like("CBE-V-90%")).delete(synchronize_session=False)
    db.commit()
    db.close()
