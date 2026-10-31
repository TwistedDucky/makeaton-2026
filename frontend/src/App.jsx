import { useEffect, useState } from "react";

function App() {
  const [message, setMessage] = useState("Connecting to Django...");

  useEffect(() => {
    fetch("/api/hello/")
      .then((response) => {
        if (!response.ok) throw new Error("Request failed");
        return response.json();
      })
      .then((data) => setMessage(data.message))
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
