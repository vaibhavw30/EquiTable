import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import UnifiedPage from './pages/UnifiedPage'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<UnifiedPage />} />
        <Route path="/map" element={<UnifiedPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
