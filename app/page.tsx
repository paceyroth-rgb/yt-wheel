"use client";

import { useEffect, useMemo, useState } from "react";

type Album = {
  title: string;
  artist: string;
  thumbnail: string;
  browseId: string;
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export default function Home() {
  const [albums, setAlbums] = useState<Album[]>([]);
  const [rotation, setRotation] = useState(0);
  const [selected, setSelected] = useState<Album | null>(null);
  const [spinning, setSpinning] = useState(false);
  const [colors, setColors] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    async function loadAlbums() {
      try {
        setLoading(true);
        setError("");

        const response = await fetch(`${API_URL}/albums`);

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
        setError("Could not reach your album library. Check that the API is running.");
      } finally {
        setLoading(false);
      }
    }

    loadAlbums();
  }, []);

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
      </section>

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
    </main>
  );
}
