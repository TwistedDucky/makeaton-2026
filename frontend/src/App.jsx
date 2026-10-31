import { useEffect, useState } from "react";
import { initializeCsrf } from "./api/auth";

function App() {
  const [message, setMessage] = useState("Connecting to Django...");

  useEffect(() => {
    initializeCsrf()
      .then((data) => {
        if (data.success) {
          setMessage("Connected to Django backend! (CSRF cookie initialized)");
        } else {
          setMessage("Failed to verify backend connection");
        }
      })
      .catch(() => setMessage("Could not connect to Django"));
  }, []);

  return (
    <main>
      <h1>Hackathon Starter</h1>
      <p>{message}</p>
    </main>
  );
}

export default App;
