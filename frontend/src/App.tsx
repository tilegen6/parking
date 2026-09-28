import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { useAuth } from "./context/AuthContext";
import { AccessListsPage } from "./pages/AccessListsPage";
import { ActiveCarsPage } from "./pages/ActiveCarsPage";
import { CamerasPage } from "./pages/CamerasPage";
import { DashboardPage } from "./pages/DashboardPage";
import { EventsPage } from "./pages/EventsPage";
import { GatesPage } from "./pages/GatesPage";
import { LoginPage } from "./pages/LoginPage";
import { PaymentPage } from "./pages/PaymentPage";
import { PayErrorPage, PaySuccessPage } from "./pages/PayResult";
import { RecognizePage } from "./pages/RecognizePage";
import { SessionDetailPage } from "./pages/SessionDetailPage";
import { SessionsPage } from "./pages/SessionsPage";
import { SimulatorPage } from "./pages/SimulatorPage";
import { StudioPage } from "./pages/StudioPage";
import { TariffsPage } from "./pages/TariffsPage";
import { UsersPage } from "./pages/UsersPage";

export default function App() {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-ink text-sm text-slate-400">
        Загрузка…
      </div>
    );
  }

  // Не авторизован — только экран входа (админ-панель за логином)
  if (!user) return <LoginPage />;

  const isAdmin = user.role === "admin";
  const canManageLists = isAdmin || user.role === "list_manager";

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
        {/* Тестовый стенд создаёт настоящие сессии — только админу */}
        {isAdmin && <Route path="studio" element={<StudioPage />} />}
        {isAdmin && <Route path="simulator" element={<SimulatorPage />} />}
        {canManageLists && (
          <Route path="access-lists" element={<AccessListsPage />} />
        )}
        {isAdmin && <Route path="users" element={<UsersPage />} />}
        <Route path="pay/success" element={<PaySuccessPage />} />
        <Route path="pay/error" element={<PayErrorPage />} />
        <Route path="pay/:sessionId" element={<PaymentPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
