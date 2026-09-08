import { readFileSync } from "node:fs";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { adaptReplay } from "../field/replayAdapter";
import { resolve } from "../field/contract";
import App from "../App";
import DepthRenderer from "../components/DepthRenderer";
import { loadReplay } from "../field/api";

const real = adaptReplay(
  JSON.parse(readFileSync("../outputs/phase7b/test-field.json", "utf8")),
);
vi.mock("../components/Plot", () => ({
  default: () => <div>Plotly chart</div>,
}));
vi.mock("../field/api", () => ({
  getJson: vi.fn(async () => ({ date_range: ["2015-01-01", "2024-12-15"] })),
  loadReplay: vi.fn(),
}));
vi.mock("three", async (original) => ({
  ...(await original<object>()),
  WebGLRenderer: class {
    constructor() {
      throw Error("Test device without WebGL");
    }
  },
}));
beforeEach(() => {
  vi.mocked(loadReplay).mockImplementation(async () => real);
  const context = new Proxy(
    {},
    {
      get: (object, key) =>
        key in object ? object[key as keyof typeof object] : () => {},
    },
  );
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(
    context as CanvasRenderingContext2D,
  );
  location.hash = "replay";
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});
it("renders actual source numbers and all depths without further fetches on controls", async () => {
  render(<App />);
  await screen.findAllByText("22.340");
  expect(loadReplay).toHaveBeenCalledTimes(1);
  expect(
    screen.getByLabelText("Depth").querySelectorAll("option"),
  ).toHaveLength(15);
  fireEvent.change(screen.getByLabelText("Depth"), { target: { value: "14" } });
  await screen.findAllByText("6.747");
  expect(loadReplay).toHaveBeenCalledTimes(1);
  fireEvent.change(screen.getByLabelText("Display layer"), {
    target: { value: "anomaly" },
  });
  expect(loadReplay).toHaveBeenCalledTimes(1);
  fireEvent.change(screen.getByLabelText("Latitude"), {
    target: { value: "15" },
  });
  fireEvent.click(screen.getByRole("button", { name: /Inspect column/ }));
  expect(loadReplay).toHaveBeenCalledTimes(1);
  expect(screen.getByTestId("zero-note")).toHaveTextContent("0.494");
  expect(screen.getByTestId("deep-note")).toHaveTextContent(
    "climatology-dominant",
  );
});
it("date changes use replay transport and force button explicitly recomputes", async () => {
  render(<App />);
  await screen.findAllByText("22.340");
  fireEvent.change(screen.getByLabelText("HISTORICAL DATE"), {
    target: { value: "2021-06-16" },
  });
  await waitFor(() => expect(loadReplay).toHaveBeenCalledTimes(2));
  expect(vi.mocked(loadReplay).mock.calls[1].slice(0, 2)).toEqual([
    "2021-06-16",
    false,
  ]);
  await screen.findAllByText("22.340");
  fireEvent.click(screen.getByRole("button", { name: "Run frozen L2" }));
  await waitFor(() => expect(loadReplay).toHaveBeenCalledTimes(3));
  expect(vi.mocked(loadReplay).mock.calls[2][1]).toBe(true);
});
it("API failure renders an explicit error with no sample reconstruction", async () => {
  vi.mocked(loadReplay).mockRejectedValueOnce(
    Error("Local inputs unavailable"),
  );
  render(<App />);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Local inputs unavailable",
  );
  expect(screen.queryByTestId("field-map")).toBeNull();
});
it("shared renderer falls back to a useful 2D view without WebGL or a backend", async () => {
  render(
    <DepthRenderer
      field={real.field}
      layer="temperature"
      depth={7}
      palette="viridis"
      selection={resolve(real.field, 15.25, 87.75)}
      exaggeration={700}
      clip={[0, 14]}
      scaleMode="field"
      explode={1}
      layerCount={5}
      onSelect={() => {}}
    />,
  );
  expect(await screen.findByRole("status")).toHaveTextContent(
    "3D view unavailable",
  );
  expect(screen.getByTestId("field-map")).toBeInTheDocument();
  expect(loadReplay).not.toHaveBeenCalled();
});
