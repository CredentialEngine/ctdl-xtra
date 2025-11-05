export const API_URL = import.meta.env.VITE_PORT
  ? `${import.meta.env.VITE_API_URL}:${import.meta.env.VITE_PORT}`
  : import.meta.env.VITE_API_URL;
