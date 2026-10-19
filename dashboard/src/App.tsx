import { useState } from "react";

import { clearSession, loadSession, saveSession, type Session } from "./api";
import { ConnectScreen } from "./ConnectScreen";
import { Workspace } from "./Workspace";

export default function App() {
  const [session, setSession] = useState<Session | null>(() => loadSession());

  function handleConnect(next: Session) {
    saveSession(next);
    setSession(next);
  }

  function handleDisconnect() {
    clearSession();
    setSession(null);
  }

  if (!session) {
    return <ConnectScreen onConnect={handleConnect} />;
  }

  return <Workspace session={session} onDisconnect={handleDisconnect} />;
}
