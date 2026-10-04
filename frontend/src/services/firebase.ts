import { getApps, initializeApp } from "firebase/app";
import {
  ConfirmationResult,
  getAuth,
  RecaptchaVerifier,
  signInWithPhoneNumber,
} from "firebase/auth";

const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
};

/**
 * Firebase rejects "localhost" as an authorised domain for phone auth, and we
 * develop on http://localhost:5173. Skipping the reCAPTCHA challenge is the
 * supported way around that -- but it only ever works with the fictional test
 * numbers from the console, never with a real phone number.
 */
const skipRecaptcha =
  import.meta.env.VITE_FIREBASE_SKIP_RECAPTCHA === "true" &&
  import.meta.env.DEV;

export const RECAPTCHA_CONTAINER_ID = "recaptcha-container";

export const FIREBASE_NOT_CONFIGURED =
  "Firebase is not configured. Add the VITE_FIREBASE_* values to frontend/.env.";

let authInstance: ReturnType<typeof getAuth> | null = null;
let verifier: RecaptchaVerifier | null = null;

export function isFirebaseConfigured(): boolean {
  return Boolean(firebaseConfig.apiKey && firebaseConfig.projectId && firebaseConfig.appId);
}

function getFirebaseAuth() {
  if (!isFirebaseConfigured()) {
    throw new Error(FIREBASE_NOT_CONFIGURED);
  }

  if (!authInstance) {
    const app = getApps().length ? getApps()[0] : initializeApp(firebaseConfig);
    authInstance = getAuth(app);

    if (skipRecaptcha) {
      authInstance.settings.appVerificationDisabledForTesting = true;
    }
  }

  return authInstance;
}

function getVerifier() {
  const auth = getFirebaseAuth();

  if (!verifier) {
    verifier = new RecaptchaVerifier(auth, RECAPTCHA_CONTAINER_ID, {
      size: "invisible",
    });
  }

  return verifier;
}

/**
 * Drop the solved reCAPTCHA so the next send attempt starts fresh. In v12
 * `reset()` is internal, and `clear()` is the public teardown that also lets us
 * build a brand new verifier on the next attempt.
 */
export function resetRecaptcha() {
  if (verifier) {
    try {
      verifier.clear();
    } catch {
      // A verifier that was never rendered throws; nothing to clean up.
    }
    verifier = null;
  }
}

/**
 * Ask Firebase to SMS a verification code. Returns a handle used later by
 * `confirmPhoneCode` once the user types the code they received.
 */
export async function sendPhoneOtp(phoneNumber: string): Promise<ConfirmationResult> {
  const auth = getFirebaseAuth();
  const appVerifier = getVerifier();
  return signInWithPhoneNumber(auth, phoneNumber, appVerifier);
}

/** Exchange the SMS code for a Firebase ID token we can hand to our backend. */
export async function confirmPhoneCode(
  confirmation: ConfirmationResult,
  code: string,
): Promise<string> {
  const result = await confirmation.confirm(code);
  return result.user.getIdToken();
}

/** Turn Firebase's opaque error codes into something a human can act on. */
export function friendlyAuthError(error: unknown): string {
  const code = (error as { code?: string })?.code ?? "";
  const message = (error as { message?: string })?.message ?? "";

  switch (code) {
    case "auth/invalid-phone-number":
      return "That phone number does not look right. Use the full number with country code, e.g. +16505550100.";
    case "auth/missing-phone-number":
      return "Enter your phone number.";
    case "auth/invalid-verification-code":
      return "That code is not correct. Check the SMS and try again.";
    case "auth/code-expired":
      return "That code has expired. Request a new one.";
    case "auth/too-many-requests":
      return "Too many attempts. Wait a few minutes and try again.";
    case "auth/invalid-app-credential":
      // Almost always the SMS region policy, which blocks every region by default.
      return "Firebase rejected this number. Check that your country is allowed under Authentication > Settings > SMS region policy.";
    case "auth/billing-not-enabled":
      return "Phone sign-in is not enabled for this Firebase project yet.";
    case "auth/unauthorized-domain":
      return "This domain is not authorised for phone sign-in.";
    case "auth/network-request-failed":
      return "Network error. Check your connection and try again.";
    default:
      return message || "Something went wrong. Please try again.";
  }
}
