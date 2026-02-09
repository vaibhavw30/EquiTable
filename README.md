# EquiTable

AI-powered food rescue agent that connects surplus food sources with communities in need.

## Project Structure

```
EquiTable/
├── backend_ml/          # FastAPI backend
│   ├── main.py          # API entry point
│   ├── models/          # Pydantic models
│   ├── services/        # Business logic services
│   └── requirements.txt # Python dependencies
├── frontend/            # React (Vite) frontend
│   └── src/
│       └── App.jsx      # Main application component
└── README.md
```

## Prerequisites

- Python 3.10+
- Node.js 18+
- MongoDB (optional, for full functionality)

## Getting Started

### Backend Setup

1. Navigate to the backend directory:
   ```bash
   cd backend_ml
   ```

2. Create and activate a virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Copy the environment template and configure:
   ```bash
   cp .env.example .env
   # Edit .env with your API keys
   ```

5. Start the backend server:
   ```bash
   uvicorn main:app --reload --host 127.0.0.1 --port 8000
   ```

   The API will be available at `http://127.0.0.1:8000`

### Frontend Setup

1. Navigate to the frontend directory:
   ```bash
   cd frontend
   ```

2. Install dependencies:
   ```bash
   npm install
   ```

3. Start the development server:
   ```bash
   npm run dev
   ```

   The app will be available at `http://localhost:5173`

## Running Both Servers Concurrently

Open two terminal windows/tabs:

**Terminal 1 - Backend:**
```bash
cd backend_ml
source venv/bin/activate
uvicorn main:app --reload
```

**Terminal 2 - Frontend:**
```bash
cd frontend
npm run dev
```

### Alternative: Using a Process Manager

You can use tools like `concurrently` or `tmux` to run both servers in a single terminal.

## API Endpoints

| Endpoint     | Method | Description                    |
|-------------|--------|--------------------------------|
| `/`         | GET    | Health check                   |
| `/api/test` | GET    | Frontend connectivity test     |

## Tech Stack

### Backend
- FastAPI - Modern async Python web framework
- Motor - Async MongoDB driver
- Pydantic - Data validation
- Firecrawl - Web scraping
- OpenAI - AI/LLM integration

### Frontend
- React 18 with Vite
- Tailwind CSS - Utility-first CSS
- Lucide React - Icon library
- @vis.gl/react-google-maps - Maps integration

## License

MIT
