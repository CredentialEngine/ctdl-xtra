import { API_URL } from "@/constants";
import { UserContext } from "@/userContext";
import { useContext, useEffect } from "react";
import { useLocation } from "wouter";

export default function Logout() {
  const [_location, navigate] = useLocation();
  const { setUser } = useContext(UserContext);

  useEffect(() => {
    fetch(`${API_URL}/logout`, {
      method: "POST",
      credentials: "include",
    }).then(() => {
      setUser(undefined);
      navigate("/");
    });
  }, []);

  return <></>;
}
