import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { ActiveCarsPage } from "./pages/ActiveCarsPage";
import { CamerasPage } from "./pages/CamerasPage";
import { DashboardPage } from "./pages/DashboardPage";
import { EventsPage } from "./pages/EventsPage";
import { GatesPage } from "./pages/GatesPage";
import { PaymentPage } from "./pages/PaymentPage";
import { PayErrorPage, PaySuccessPage } from "./pages/PayResult";
import { RecognizePage } from "./pages/RecognizePage";
import { SessionDetailPage } from "./pages/SessionDetailPage";
import { SessionsPage } from "./pages/SessionsPage";
import { SimulatorPage } from "./pages/SimulatorPage";
import { StudioPage } from "./pages/StudioPage";
import { TariffsPage } from "./pages/TariffsPage";

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
        <Route path="gates" element={<GatesPage />} />
        <Route path="recognize" element={<RecognizePage />} />
        <Route path="tariffs" element={<TariffsPage />} />
        <Route path="studio" element={<StudioPage />} />
        <Route path="simulator" element={<SimulatorPage />} />
        <Route path="pay/success" element={<PaySuccessPage />} />
        <Route path="pay/error" element={<PayErrorPage />} />
        <Route path="pay/:sessionId" element={<PaymentPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
