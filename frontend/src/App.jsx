import { AuthProvider } from "./context/AuthContext";
import Layout from "./components/layout/Layout";
import DashboardPage from "./pages/dashboard/DashboardPage";

function App() {
  return (
    <AuthProvider>
      <Layout>
        {/* TODO: replace with a router (e.g. react-router-dom) */}
        <DashboardPage />
      </Layout>
    </AuthProvider>
  );
}

export default App;
