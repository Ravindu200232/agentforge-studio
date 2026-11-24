import * as React from "react";
import { accounts, signInRoute, signUp, type Account } from "@/demo";
import { navigate } from "@/lib/router";

// Who is signed in, for a prototype that has sign-in. The accounts are fictitious, one for each role, and they are the ones the
// finished application is seeded with. Nothing is stored: a reload signs out. `src/demo.ts` is written by the Studio.

export type User = Account;

type Session = {
  user: User | null;
  accounts: Account[];
  /** Sign in with a demo email and password. Returns the account, or null when they do not match. */
  signIn: (email: string, password: string) => User | null;
  /** One click: sign in as the account for a role (its key or name) or an email. */
  signInAs: (roleOrEmail: string) => User | null;
  /** Sign up as the role that sign-ups get, under the name and email that were typed. */
  signUp: (name: string, email: string) => User | null;
  signOut: () => void;
  canOpen: (route: string) => boolean;
};

const find = (value: string) => {
  const key = String(value || "").trim().toLowerCase();
  return accounts.find((a) => [a.roleKey, a.role, a.email].some((v) => String(v || "").toLowerCase() === key)) || null;
};

const SessionContext = React.createContext<Session | null>(null);

export function SessionProvider({ children }: { children: React.ReactNode }) {
  // `?as=<email or role>` opens the app already signed in (how the Studio looks at a signed-in page).
  const [user, setUser] = React.useState<User | null>(() => find(new URLSearchParams(window.location.search).get("as") || ""));

  // Who is signed in, as the Studio's browser reads it when it clicks through the prototype.
  React.useEffect(() => {
    (window as unknown as { __afUser?: string }).__afUser = user?.email || "";
  }, [user]);

  const value = React.useMemo<Session>(() => {
    const enter = (account: User | null, own?: Partial<User>) => {
      if (!account) return null;
      const next = { ...account, ...own };
      setUser(next);
      navigate(account.landsOn);
      return next;
    };
    return {
      user,
      accounts,
      signIn: (email, password) => {
        const account = find(email);
        return account && account.password === String(password || "") ? enter(account) : null;
      },
      signInAs: (roleOrEmail) => enter(find(roleOrEmail)),
      signUp: (name, email) => {
        const account = (signUp && find(signUp.roleKey)) || accounts[0] || null;
        return enter(account, { name: String(name || "").trim() || account?.name, email: String(email || "").trim() || account?.email });
      },
      signOut: () => {
        setUser(null);
        navigate(signInRoute || "/");
      },
      canOpen: (route) => !user || user.canOpen.includes(route),
    };
  }, [user]);

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): Session {
  const session = React.useContext(SessionContext);
  if (!session) throw new Error("useSession must be used inside the SessionProvider (it is in src/App.tsx)");
  return session;
}
