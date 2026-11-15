import { useEffect, useState } from "react";
import { request } from "../api/client";

export default function useSmsAvailability() {
  const [available, setAvailable] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    request("/api/v1/users/auth-capabilities/", { signal: controller.signal })
      .then((data) => setAvailable(data?.sms_available === true))
      .catch(() => setAvailable(false));
    return () => controller.abort();
  }, []);
  return available;
}
