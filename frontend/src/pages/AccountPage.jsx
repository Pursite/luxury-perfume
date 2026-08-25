import { useCallback, useEffect, useRef, useState } from "react";

import { getCurrentProfile, updateProfile } from "../api/profile";
import AccountDetailsForm from "../components/AccountDetailsForm";
import AddressEditor from "../components/AddressEditor";
import ErrorState from "../components/ErrorState";
import { AccountSkeleton } from "../components/LoadingSkeletons";
import UnavailableControl from "../components/UnavailableControl";
import useDocumentTitle from "../hooks/useDocumentTitle";

function missingDetails(profile) {
  const missing = [];
  if (!profile.username) missing.push("Username");
  if (!profile.email) missing.push("Email");
  if (!profile.first_name) missing.push("First name");
  if (!profile.last_name) missing.push("Last name");
  if (!profile.addresses.length) missing.push("Address");
  if (!profile.phone_number) missing.push("Verified phone number");
  return missing;
}

export default function AccountPage() {
  useDocumentTitle("Account Details");
  const [profile, setProfile] = useState(null);
  const [error, setError] = useState("");
  const [requestVersion, setRequestVersion] = useState(0);
  const mutationQueue = useRef(Promise.resolve());

  useEffect(() => {
    const controller = new AbortController();
    getCurrentProfile(controller.signal)
      .then((response) => setProfile(response.data))
      .catch((caught) => {
        if (caught.name !== "AbortError") {
          setError("Your account details could not be loaded. Check your connection and try again.");
        }
      });
    return () => controller.abort();
  }, [requestVersion]);

  const retry = useCallback(() => {
    setError("");
    setProfile(null);
    setRequestVersion((current) => current + 1);
  }, []);

  const saveProfile = useCallback((payload) => {
    const request = mutationQueue.current.then(() => updateProfile(payload));
    mutationQueue.current = request.catch(() => undefined);
    return request;
  }, []);

  if (error && !profile) {
    return (
      <div className="account-page page-frame">
        <ErrorState
          title="Account details are unavailable."
          message={error}
          onRetry={retry}
        />
      </div>
    );
  }

  if (!profile) {
    return <div className="account-page page-frame"><AccountSkeleton /></div>;
  }

  const missing = missingDetails(profile);
  return (
    <section className="account-page page-frame" aria-labelledby="account-title">
      <header className="account-masthead">
        <div>
          <p className="eyebrow">Your profile</p>
          <h1 id="account-title">Account Details</h1>
        </div>
        <span className={`profile-completion ${profile.is_profile_complete ? "is-complete" : "is-incomplete"}`}>
          {profile.is_profile_complete ? "Profile complete" : "Profile incomplete"}
        </span>
      </header>

      {!profile.is_profile_complete && missing.length ? (
        <aside className="profile-guidance" aria-labelledby="profile-guidance-title">
          <h2 id="profile-guidance-title">Complete your profile</h2>
          <p>Still needed: {missing.join(", ")}.</p>
          {!profile.phone_number ? (
            <p>Phone verification is not available yet. You can continue saving every other detail.</p>
          ) : null}
        </aside>
      ) : null}

      <AccountDetailsForm profile={profile} onProfileChange={setProfile} saveProfile={saveProfile} />

      <section className="account-ledger-section" aria-labelledby="address-heading">
        <div className="account-section-heading">
          <p className="eyebrow">Delivery</p>
          <h2 id="address-heading">Address</h2>
        </div>
        <div className="address-list">
          {profile.addresses.length ? profile.addresses.map((address) => (
            <AddressEditor
              key={address.id}
              address={address}
              onProfileChange={setProfile}
              saveProfile={saveProfile}
            />
          )) : (
            <AddressEditor key="new-address" onProfileChange={setProfile} saveProfile={saveProfile} />
          )}
        </div>
      </section>

      <section className="account-ledger-section account-security" aria-labelledby="security-heading">
        <div className="account-section-heading">
          <p className="eyebrow">Credentials</p>
          <h2 id="security-heading">Security</h2>
        </div>
        <div>
          <p>Password reset requires SMS verification, which is not available yet.</p>
          <UnavailableControl label="Reset Password" />
        </div>
      </section>
    </section>
  );
}
