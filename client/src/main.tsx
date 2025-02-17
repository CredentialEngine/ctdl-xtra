import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { httpBatchLink } from "@trpc/client";
import React from "react";
import ReactDOM from "react-dom/client";
import { Scaffold } from "./components/app/routes";
import Unauthenticated from "./components/app/unauthenticated";
import { API_URL } from "./constants";
import "./main.css";
import { UserProvider } from "./userContext";
import { trpc } from "./utils";
import { Dashboard } from "./components/app/dashboard";
import { WithUser } from "./components/app/withUser";

const queryClient = new QueryClient();
const trpcClient = trpc.createClient({
  links: [
    httpBatchLink({
      fetch(url, options) {
        return fetch(url, {
          ...options,
          credentials: "include",
        });
      },
      url: `${API_URL}/trpc`,
    }),
  ],
});

export function App() {
  return (
    <React.StrictMode>
    <trpc.Provider client={trpcClient} queryClient={queryClient}>
      <QueryClientProvider client={queryClient}>
        <UserProvider>
          <WithUser 
            IfAuth={<Scaffold><Dashboard /></Scaffold>}
            Else={<Unauthenticated />}
          />
        </UserProvider>
      </QueryClientProvider>
    </trpc.Provider>
  </React.StrictMode>
    
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(<App />);
