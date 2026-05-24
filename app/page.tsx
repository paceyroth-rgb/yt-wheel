"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

type Album = {
  title: string;
  artist: string;
  thumbnail: string;
  browseId: string;
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
const API_BASE = API_URL.replace(/\/$/, "");
const SESSION_STORAGE_KEY = "ytwheel_session";

type AuthFlow = {
  sessionId: string;
  userCode: string;
  verificationUrl: string;
  expiresIn: number;
  interval: number;
};

function getStoredSessionId() {
  if (typeof window === "undefined") return "";

  return window.localStorage.getItem(SESSION_STORAGE_KEY) ?? "";
}

function setStoredSessionId(sessionId: string) {
  if (typeof window === "undefined") return;

  window.localStorage.setItem(SESSION_STORAGE_KEY, sessionId);
}

function clearStoredSessionId() {
  if (typeof window === "undefined") return;

  window.localStorage.removeItem(SESSION_STORAGE_KEY);
}

function sessionHeaders() {
  const sessionId = getStoredSessionId();

  return sessionId ? { "X-Ytwheel-Session": sessionId } : undefined;
}

export default function Home() {
  const [albums, setAlbums] = useState<Album[]>([]);
  const [rotation, setRotation] = useState(0);
  const [selected, setSelected] = useState<Album | null>(null);
  const [spinning, setSpinning] = useState(false);
  const [colors, setColors] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [authenticated, setAuthenticated] = useState(false);
  const [authFlow, setAuthFlow] = useState<AuthFlow | null>(null);
  const [authStartedAt, setAuthStartedAt] = useState<number | null>(null);
  const [authLoading, setAuthLoading] = useState(false);

  const loadAlbums = useCallback(async () => {
    try {
      setLoading(true);
      setError("");

      const response = await fetch(`${API_BASE}/albums`, {
        credentials: "include",
        headers: sessionHeaders(),
      });

      if (!response.ok) {
        throw new Error("Album library could not be loaded.");
      }

      const data = await response.json();

      const loadedAlbums = data.albums ?? [];

setAlbums(loadedAlbums);
      setColors(
        loadedAlbums.map((_: Album, index: number) => {
          const hue = (index * 47 + Math.floor(Math.random() * 28)) % 360;
          return `hsl(${hue}, 78%, 58%)`;
        }),
      );
    } catch {
      setAuthenticated(false);
      setError("Could not reach your album library. Sign in again or check that the API is running.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    async function checkAuth() {
      try {
        setLoading(true);
        setError("");

        const response = await fetch(`${API_BASE}/auth/status`, {
          credentials: "include",
          headers: sessionHeaders(),
        });

        if (!response.ok) {
          throw new Error("Login status could not be loaded.");
        }

        const data = await response.json();

        const isAuthenticated = Boolean(data.authenticated);

        setAuthenticated(isAuthenticated);

        if (isAuthenticated) {
          await loadAlbums();
        }
      } catch {
        setError("Could not reach the login service. Check that the API is running.");
      } finally {
        setLoading(false);
      }
    }

    checkAuth();
  }, [loadAlbums]);

  useEffect(() => {
    if (!authFlow || authenticated) return;

    const expiresAt = (authStartedAt ?? Date.now()) + authFlow.expiresIn * 1000;

    const pollInterval = window.setInterval(async () => {
      if (Date.now() >= expiresAt) {
        setError("The Google login code expired. Start sign in again for a fresh code.");
        setAuthFlow(null);
        setAuthStartedAt(null);
        return;
      }

      try {
        const response = await fetch(`${API_BASE}/auth/poll`, {
          method: "POST",
          credentials: "include",
          headers: sessionHeaders(),
        });

        if (response.status === 202) return;

        if (!response.ok) {
          const data = await response.json().catch(() => null);
          const detail = String(data?.detail ?? "");

          throw new Error(detail || "Login was not completed.");
        }

        setAuthenticated(true);
        setAuthFlow(null);
        setAuthStartedAt(null);
        await loadAlbums();
      } catch (pollError) {
        setError(
          pollError instanceof Error
            ? `Google login was not completed. ${pollError.message}`
            : "Google login was not completed. Try signing in again.",
        );
        setAuthFlow(null);
        setAuthStartedAt(null);
      }
    }, Math.max(authFlow.interval, 5) * 1000);

    return () => window.clearInterval(pollInterval);
  }, [authFlow, authStartedAt, authenticated, loadAlbums]);

  async function loadDevLibrary() {

  try {

    setLoading(true);

    setError("");

    const response = await fetch(`${API_BASE}/albums/dev`);

    if (!response.ok) {
      throw new Error("Developer library could not be loaded.");
    }

    const data = await response.json();

    const loadedAlbums = data.albums ?? [];

    setAlbums(loadedAlbums);

    setColors(
      loadedAlbums.map((_: Album, index: number) => {
        const hue = (index * 47 + Math.floor(Math.random() * 28)) % 360;
        return `hsl(${hue}, 78%, 58%)`;
      }),
    );

    setAuthenticated(true);

  } catch {

    setError("Could not load developer library.");

  } finally {

    setLoading(false);

  }
}

  async function startLogin() {
    try {
      setAuthLoading(true);
      setError("");

      const response = await fetch(`${API_BASE}/auth/start`, {
        method: "POST",
        credentials: "include",
        headers: sessionHeaders(),
      });

      if (!response.ok) {
        const data = await response.json().catch(() => null);
        throw new Error(data?.detail ?? "Login could not be started.");
      }

      const data = await response.json();
      setStoredSessionId(data.sessionId);
      setAuthFlow(data);
      setAuthStartedAt(Date.now());
    } catch (loginError) {
      setError(
        loginError instanceof Error
          ? `Could not start Google login. ${loginError.message}`
          : "Could not start Google login. Check the OAuth client file and backend logs.",
      );
    } finally {
      setAuthLoading(false);
    }
  }

  async function logout() {
    await fetch(`${API_BASE}/auth/logout`, {
      method: "POST",
      credentials: "include",
      headers: sessionHeaders(),
    });

    clearStoredSessionId();
    setAuthenticated(false);
    setAuthFlow(null);
    setAuthStartedAt(null);
    setAlbums([]);
    setSelected(null);
  }

  function spin() {
    if (albums.length === 0 || spinning) return;

    setSpinning(true);
    setSelected(null);

    const randomIndex = Math.floor(Math.random() * albums.length);
    const segmentSize = 360 / albums.length;
    const targetAngle = randomIndex * segmentSize + segmentSize / 2;
    const currentAngle = rotation % 360;
    const pointerAngle = 270;
    const degreesToTarget = (pointerAngle - targetAngle - currentAngle + 360) % 360;
    const extraRotation = 1800 + degreesToTarget;
    const newRotation = rotation + extraRotation;

    setRotation(newRotation);

    window.setTimeout(() => {
      setSelected(albums[randomIndex]);
      setSpinning(false);
    }, 2500);
  }

  const wheelBackground = useMemo(() => {
    if (albums.length === 0) {
      return "conic-gradient(#2a2f3a, #181b22)";
    }

    return `conic-gradient(${albums
      .map((_, index) => {
        const start = (index / albums.length) * 360;
        const end = ((index + 1) / albums.length) * 360;

        return `${colors[index]} ${start}deg ${end}deg`;
      })
      .join(",")})`;
  }, [albums, colors]);

  const hasAlbumLink = selected?.browseId;

  return (
    <main className="app-shell">
      <section className="app-header">
        <p className="eyebrow">YouTube Music roulette</p>
        <h1>YT Album Wheel</h1>
        <p className="lede">
          Spin through your saved albums and let the library pick what plays next.
        </p>
        {authenticated && (
          <button className="text-button" onClick={logout}>
            Sign out
          </button>
        )}
      </section>

      {!authenticated && (
        <section className="login-panel" aria-label="YouTube Music login">
          <div>
            <p className="result-label">Connect your library</p>
            <h2>Sign in with Google to build your wheel</h2>
            <p>
              The app will show a short code. Approve it with the same Google account
              you use for YouTube Music.
            </p>
          </div>
          <button
            className="spin-button"
            disabled={loading}
            onClick={loadDevLibrary}
            style={{ marginBottom: "16px" }}
          >
            Load Developer Library
          </button>
          {authFlow ? (
            <div className="login-code">
              <div className="login-code-copy">
                <p className="result-label">Enter this code</p>
                <span>{authFlow.userCode}</span>
              </div>
              <a
                className="album-link"
                href={authFlow.verificationUrl}
                rel="noopener noreferrer"
                target="_blank"
              >
                Open Google login
              </a>
              <p>
                Keep this tab open, enter the code on Google&apos;s page, then approve access.
              </p>
            </div>
          ) : (
            <button className="spin-button" disabled={loading || authLoading} onClick={startLogin}>
              {authLoading ? "Starting..." : "Sign in"}
            </button>
          )}

          {error && <p className="status-message">{error}</p>}
        </section>
      )}

      {authenticated && (
        <section className="wheel-layout" aria-label="Album wheel picker">
        <div className="wheel-panel">
          <div className="wheel-stage">
            <div className="wheel-pointer" aria-hidden="true" />
            <div
              className="wheel"
              style={{
                background: wheelBackground,
                transform: `rotate(${rotation}deg)`,
                transition: spinning
                  ? "transform 2.5s cubic-bezier(0.2, 0.8, 0.2, 1)"
                  : "none",
              }}
            >
              <div className="wheel-center">
                <span>{albums.length}</span>
                <small>albums</small>
              </div>
            </div>
          </div>

          <button
            className="spin-button"
            disabled={loading || spinning || albums.length === 0}
            onClick={spin}
          >
            {spinning ? "Spinning..." : "Spin"}
          </button>

          {error && <p className="status-message">{error}</p>}
          {!error && loading && <p className="status-message">Loading your albums...</p>}
        </div>

        <aside className="result-panel" aria-live="polite">
          {selected ? (
            <>
              <div className="album-art-wrap">
                {selected.thumbnail ? (
                  <img
                    className="album-art"
                    src={selected.thumbnail}
                    alt={`${selected.title} album artwork`}
                  />
                ) : (
                  <div className="album-art album-art-empty">No artwork</div>
                )}
              </div>

              <div className="album-copy">
                <p className="result-label">Tonight&apos;s pick</p>
                <h2>{selected.title}</h2>
                <p>{selected.artist}</p>
              </div>

              {hasAlbumLink && (
                <a
                  className="album-link"
                  href={`https://music.youtube.com/browse/${selected.browseId}`}
                  rel="noopener noreferrer"
                  target="_blank"
                >
                  Open in YouTube Music
                </a>
              )}
            </>
          ) : (
            <div className="empty-result">
              <p className="result-label">Ready when you are</p>
              <h2>{loading ? "Building the wheel" : "Spin to choose an album"}</h2>
              <p>
                Your result will land here next to the wheel, so the page stays
                balanced instead of stretching downward.
              </p>
            </div>
          )}
        </aside>
      </section>
      )}
    </main>
  );
}
