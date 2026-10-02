import { lazy, Suspense, type ReactNode } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Loading } from "./components/ui";
import PanelLayout from "./layouts/PanelLayout";
import PublicLayout from "./layouts/PublicLayout";
import { isPanelUser, useAuth, type Role } from "./lib/auth";
import Home from "./pages/public/Home";
import Login from "./pages/public/Login";
import ProductDetail from "./pages/public/ProductDetail";

const StoreDetail = lazy(() => import("./pages/public/StoreDetail"));
const Report = lazy(() => import("./pages/public/Report"));
const Track = lazy(() => import("./pages/public/Track"));
const Subsidized = lazy(() => import("./pages/public/Subsidized"));
const Observatory = lazy(() => import("./pages/public/Observatory"));
const RegisterStore = lazy(() => import("./pages/public/RegisterStore"));
const Account = lazy(() => import("./pages/public/Account"));
const MapPage = lazy(() => import("./pages/public/MapPage"));

const Dashboard = lazy(() => import("./pages/panel/Dashboard"));
const Stores = lazy(() => import("./pages/panel/Stores"));
const Products = lazy(() => import("./pages/panel/Products"));
const Prices = lazy(() => import("./pages/panel/Prices"));
const Complaints = lazy(() => import("./pages/panel/Complaints"));
const ComplaintDetail = lazy(() => import("./pages/panel/ComplaintDetail"));
const Quotas = lazy(() => import("./pages/panel/Quotas"));
const Allocations = lazy(() => import("./pages/panel/Allocations"));
const Alerts = lazy(() => import("./pages/panel/Alerts"));
const Reports = lazy(() => import("./pages/panel/Reports"));
const CommodityReports = lazy(() => import("./pages/panel/CommodityReports"));
const Org = lazy(() => import("./pages/panel/Org"));
const Slides = lazy(() => import("./pages/panel/Slides"));
const StoreProfile = lazy(() => import("./pages/panel/StoreProfile"));
const MyShop = lazy(() => import("./pages/panel/MyShop"));
const Notifications = lazy(() => import("./pages/panel/Notifications"));

function RequireAuth({ children, roles }: { children: ReactNode; roles?: Role[] }) {
  const { user, loading } = useAuth();
  const loc = useLocation();
  if (loading) return <Loading />;
  if (!user) return <Navigate to={`/login?next=${encodeURIComponent(loc.pathname + loc.search)}`} replace />;
  if (roles && !roles.includes(user.role) && user.role !== "admin") return <Navigate to="/panel" replace />;
  return <>{children}</>;
}

function RequirePanel({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  if (user && !isPanelUser(user)) return <Navigate to="/account" replace />;
  return <>{children}</>;
}

const MANAGERS: Role[] = ["governorate", "chamber", "union"];

export default function App() {
  return (
    <Suspense fallback={<Loading />}>
      <Routes>
        <Route element={<PublicLayout />}>
          <Route index element={<Home />} />
          <Route path="p/:id" element={<ProductDetail />} />
          <Route path="s/:id" element={<StoreDetail />} />
          <Route path="map" element={<MapPage />} />
          <Route path="track" element={<Track />} />
          <Route path="subsidized" element={<Subsidized />} />
          <Route path="observatory" element={<Observatory />} />
          <Route path="login" element={<Login />} />
          <Route path="report" element={<RequireAuth><Report /></RequireAuth>} />
          <Route path="register-store" element={<RequireAuth><RegisterStore /></RequireAuth>} />
          <Route path="account" element={<RequireAuth><Account /></RequireAuth>} />
        </Route>
        <Route path="panel" element={<RequireAuth><RequirePanel><PanelLayout /></RequirePanel></RequireAuth>}>
          <Route index element={<Dashboard />} />
          <Route path="notifications" element={<Notifications />} />
          <Route path="stores" element={<RequireAuth roles={MANAGERS}><Stores /></RequireAuth>} />
          <Route path="products" element={<RequireAuth roles={MANAGERS}><Products /></RequireAuth>} />
          <Route path="prices" element={<RequireAuth roles={["store"]}><Prices /></RequireAuth>} />
          <Route path="profile" element={<RequireAuth roles={["store"]}><StoreProfile /></RequireAuth>} />
          <Route path="my-shop" element={<RequireAuth roles={["store"]}><MyShop /></RequireAuth>} />
          <Route path="complaints" element={<Complaints />} />
          <Route path="complaints/:id" element={<ComplaintDetail />} />
          <Route path="quotas" element={<RequireAuth roles={["union", "store", "chamber", "governorate"]}><Quotas /></RequireAuth>} />
          <Route path="allocations" element={<RequireAuth roles={MANAGERS}><Allocations /></RequireAuth>} />
          <Route path="alerts" element={<RequireAuth roles={MANAGERS}><Alerts /></RequireAuth>} />
          <Route path="reports" element={<RequireAuth roles={MANAGERS}><Reports /></RequireAuth>} />
          <Route path="observatory" element={<RequireAuth roles={["governorate", "chamber", "union"]}><CommodityReports /></RequireAuth>} />
          <Route path="org/:entity" element={<RequireAuth roles={["governorate", "chamber"]}><Org /></RequireAuth>} />
          <Route path="slides" element={<RequireAuth roles={[]}><Slides /></RequireAuth>} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  );
}
