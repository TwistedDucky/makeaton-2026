import { useAuth } from "../context/AuthContext";

/**
 * Returns the currently logged-in user and whether the session is loading.
 */
export function useCurrentUser() {
  const { user, loading } = useAuth();
  return { user, loading };
}

