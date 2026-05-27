"use client";

import { useState, useEffect } from "react";
import { getUserId, setUserId, readCookieUserId, authMe, authLogout, type AuthUserResponse } from "@/lib/api";

function setUserIdCookie(userId: string | null) {
  document.cookie = `research_user_id=${userId ?? ""}; path=/; SameSite=Lax; max-age=${userId ? 31536000 : 0}`;
}

export default function UserSwitcher() {
  const [currentId, setCurrentId] = useState("default");
  const [editing, setEditing] = useState(false);
  const [inputVal, setInputVal] = useState("");
  const [authUser, setAuthUser] = useState<AuthUserResponse | null>(null);
  const [authMode, setAuthMode] = useState(false);

  useEffect(() => {
    authMe().then((user) => {
      if (user && user.auth_mode === "session") {
        setAuthUser(user);
        setAuthMode(true);
      } else {
        setAuthMode(false);
        const fromStorage = localStorage.getItem("research_user_id");
        if (fromStorage && /^[A-Za-z0-9_\-.]{1,64}$/.test(fromStorage)) {
          setCurrentId(fromStorage);
        } else {
          const fromCookie = readCookieUserId();
          if (fromCookie) {
            localStorage.setItem("research_user_id", fromCookie);
            setCurrentId(fromCookie);
          } else {
            setCurrentId("default");
          }
        }
      }
    }).catch(() => {
      const fromStorage = localStorage.getItem("research_user_id");
      if (fromStorage && /^[A-Za-z0-9_\-.]{1,64}$/.test(fromStorage)) {
        setCurrentId(fromStorage);
      }
    });
  }, []);

  const handleLogout = async () => {
    try {
      await authLogout();
    } catch {}
    setAuthUser(null);
    setAuthMode(false);
    window.location.href = "/login";
  };

  if (authMode && authUser) {
    return (
      <div className="flex items-center gap-2">
        <span className="text-xs text-gray-600">
          {authUser.display_name || authUser.email}
        </span>
        <button
          onClick={handleLogout}
          className="px-2 py-0.5 text-xs text-red-500 hover:text-red-700 hover:bg-red-50 rounded"
        >
          登出
        </button>
      </div>
    );
  }

  const handleSave = () => {
    const trimmed = inputVal.trim();
    if (trimmed && /^[A-Za-z0-9_\-.]{1,64}$/.test(trimmed)) {
      setUserId(trimmed);
      setUserIdCookie(trimmed);
      setCurrentId(trimmed);
      setEditing(false);
      setInputVal("");
      window.location.reload();
    }
  };

  const handleReset = () => {
    setUserId("");
    setUserIdCookie(null);
    setCurrentId("default");
    setEditing(false);
    setInputVal("");
    window.location.reload();
  };

  if (editing) {
    return (
      <div className="flex items-center gap-1">
        <input
          type="text"
          value={inputVal}
          onChange={(e) => setInputVal(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSave()}
          placeholder="user_id"
          maxLength={64}
          className="w-24 px-1.5 py-0.5 text-xs border border-gray-300 rounded focus:outline-none focus:border-blue-400"
          autoFocus
        />
        <button
          onClick={handleSave}
          className="px-1.5 py-0.5 text-xs bg-blue-500 text-white rounded hover:bg-blue-600"
        >
          OK
        </button>
        <button
          onClick={() => setEditing(false)}
          className="px-1.5 py-0.5 text-xs text-gray-500 hover:text-gray-700"
        >
          ×
        </button>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-1">
      <span
        className="text-xs text-gray-500 cursor-pointer hover:text-blue-600"
        onClick={() => {
          setInputVal(currentId === "default" ? "" : currentId);
          setEditing(true);
        }}
        title="点击切换用户"
      >
        用户 {currentId}
      </span>
      {currentId !== "default" && (
        <button
          onClick={handleReset}
          className="text-xs text-gray-400 hover:text-red-500"
          title="重置为 default"
        >
          重置
        </button>
      )}
    </div>
  );
}
