import { Link } from "react-router-dom";
import AuthLayout from "../components/AuthLayout";
import PasswordManagement from "../components/PasswordManagement";
import useSmsAvailability from "../hooks/useSmsAvailability";

export default function RecoveryPage() {
  const available = useSmsAvailability();
  return (
    <AuthLayout titleId="recovery-title" eyebrow="Account recovery" title="Reset your password" description="Verify your phone number to recover your account.">
      {available ? <PasswordManagement recovery /> : <p>SMS password recovery is currently unavailable.</p>}
      <Link to="/login">Back to sign in</Link>
    </AuthLayout>
  );
}
