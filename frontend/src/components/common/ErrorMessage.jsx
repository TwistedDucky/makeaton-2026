import { getErrorMessage } from "../../utils/errors";

export default function ErrorMessage({ error }) {
  if (!error) return null;
  return (
    <p role="alert" style={{ color: "crimson", margin: "8px 0" }}>
      {getErrorMessage(error)}
    </p>
  );
}

