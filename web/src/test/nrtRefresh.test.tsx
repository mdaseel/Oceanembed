import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useNrtStates } from "../components/hazard/useNrtStates";

afterEach(() => vi.unstubAllGlobals());
describe("latest source discovery", () => {
  it("waits for refreshed discovery before requesting the newest field", async () => {
    const calls: string[] = [];
    let finish!: (v: Response) => void;
    vi.stubGlobal("fetch", vi.fn((url: string) => {
      calls.push(url);
      if (url.includes("available-dates")) return new Promise<Response>((resolve) => { finish = resolve; });
      return Promise.resolve(new Response(JSON.stringify({ state: "UNAVAILABLE", field: null })));
    }));
    const { result } = renderHook(() => useNrtStates(false));
    let pending!: Promise<void>;
    act(() => { pending = result.current.refresh(); });
    expect(result.current.busy).toBe(true);
    expect(calls).toEqual(["/api/latest/available-dates?refresh=true"]);
    await act(async () => {
      finish(new Response(JSON.stringify({ newest_qualified_date: "2026-09-21", days: [] })));
      await pending;
    });
    expect(calls).toEqual(["/api/latest/available-dates?refresh=true", "/api/latest/qualified"]);
    expect(result.current.window7?.newest_qualified_date).toBe("2026-09-21");
    expect(result.current.busy).toBe(false);
  });
  it("exposes a discovery error instead of silently calling stale dates current", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => new Response(JSON.stringify(
      url.includes("available-dates") ? { error: "Provider unavailable", days: [] } : { state: "UNAVAILABLE", field: null },
    ))));
    const { result } = renderHook(() => useNrtStates(false));
    await act(async () => { await result.current.refresh(); });
    await waitFor(() => expect(result.current.windowError).toBe("Provider unavailable"));
    expect(result.current.checkedAt).toBeNull();
    expect(result.current.busy).toBe(false);
  });
});
