import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { ActiveCarsPage } from "./pages/ActiveCarsPage";
import { CamerasPage } from "./pages/CamerasPage";
import { DashboardPage } from "./pages/DashboardPage";
import { EventsPage } from "./pages/EventsPage";
import { RecognizePage } from "./pages/RecognizePage";
import { SessionDetailPage } from "./pages/SessionDetailPage";
import { SessionsPage } from "./pages/SessionsPage";
import { SimulatorPage } from "./pages/SimulatorPage";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<DashboardPage />} />
        <Route path="events" element={<EventsPage />} />
        <Route path="sessions" element={<SessionsPage />} />
        <Route path="sessions/:id" element={<SessionDetailPage />} />
        <Route path="active" element={<ActiveCarsPage />} />
        <Route path="cameras" element={<CamerasPage />} />
        <Route path="recognize" element={<RecognizePage />} />
        <Route path="simulator" element={<SimulatorPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
