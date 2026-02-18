import MapExperience from '../components/MapExperience'
import { useNavigate } from 'react-router-dom'

// Thin wrapper — MapExperience contains all the logic
export default function MapPage() {
  const navigate = useNavigate()

  return (
    <div className="h-screen w-screen overflow-hidden">
      <MapExperience onClose={() => navigate('/')} />
    </div>
  )
}
