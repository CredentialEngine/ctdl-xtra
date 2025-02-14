import { useContext, useEffect, useState, ReactNode } from "react";
import { API_URL } from "@/constants";
import { UserContext } from "@/userContext";

type WithUserProps = {
  IfAuth: ReactNode,
  Else: ReactNode,
}

export function WithUser({ IfAuth, Else }: WithUserProps) {
  const [isLoading, setIsLoading] = useState(true);
  const { user, setUser } = useContext(UserContext);

  useEffect(() => {
    setIsLoading(true);
    fetch(`${API_URL}/me`, { credentials: "include" })
      .then((r) => {
        if (r.status != 200) {
          throw new Error("Not authorized");
        }
        return r.json();
      })
      .then(setUser)
      .then(() => setIsLoading(false))
      .catch(() => {
        setIsLoading(false);
      });
  }, []);

  if (isLoading) {
    return null;
  }
  
  return user
      ? IfAuth
      : Else
}
