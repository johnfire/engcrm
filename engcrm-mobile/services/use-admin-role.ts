import { useEffect, useState } from "react";
import { getRole } from "./auth";

export function useAdminRole(): boolean | null {
  const [isAdmin, setIsAdmin] = useState<boolean | null>(null);
  useEffect(() => {
    let active = true;
    getRole().then((role) => { if (active) setIsAdmin(role === "admin"); })
      .catch(() => { if (active) setIsAdmin(false); });
    return () => { active = false; };
  }, []);
  return isAdmin;
}
