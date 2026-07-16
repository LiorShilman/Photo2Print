import { NavLink, Route, Routes } from "react-router-dom";
import { IconPrinter } from "./components/icons";
import UploadPage from "./pages/UploadPage";
import JobPage from "./pages/JobPage";
import HistoryPage from "./pages/HistoryPage";
import SettingsPage from "./pages/SettingsPage";

export default function App() {
  return (
    <>
      <header className="app-header">
        <NavLink to="/" className="logo" style={{ display: "flex", alignItems: "center", gap: "0.55rem" }}>
          <IconPrinter size={22} style={{ color: "#818cf8" }} />
          <span>Photo2Print</span>
        </NavLink>
        <nav>
          <NavLink to="/" end>העלאה</NavLink>
          <NavLink to="/history">היסטוריה</NavLink>
          <NavLink to="/settings">הגדרות</NavLink>
        </nav>
      </header>
      <main className="page">
        <Routes>
          <Route path="/" element={<UploadPage />} />
          <Route path="/jobs/:id" element={<JobPage />} />
          <Route path="/history" element={<HistoryPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
      </main>
    </>
  );
}
