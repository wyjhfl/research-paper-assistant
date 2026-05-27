import { cookies } from "next/headers";

const USER_ID_RE = /^[A-Za-z0-9_\-.]{1,64}$/;

export async function getServerUserId(): Promise<string> {
  try {
    const cookieStore = await cookies();
    const userId = cookieStore.get("research_user_id")?.value;
    if (userId && USER_ID_RE.test(userId)) {
      return userId;
    }
  } catch {
    // cookies() not available (e.g. during static generation)
  }
  return "default";
}
