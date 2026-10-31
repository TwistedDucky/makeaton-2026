/**
 * Returns a user-friendly message from an API error object.
 * @param {unknown} error
 * @returns {string}
 */
export function getErrorMessage(error) {
  if (!error) return "An unexpected error occurred.";
  if (typeof error === "string") return error;
  if (error.detail) return error.detail;
  if (error.message) return error.message;

  const firstKey = Object.keys(error)[0];
  if (firstKey) {
    const val = error[firstKey];
    return `${firstKey}: ${Array.isArray(val) ? val.join(", ") : val}`;
  }

  return "An unexpected error occurred.";
}

