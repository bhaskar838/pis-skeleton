import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  cn,
  EmptyState,
  ErrorState,
  Field,
  ForbiddenState,
  formatDateTime,
  formatMoneyMinor,
  formatNumber,
  Input,
  LoadingState,
  Notice,
  PageHeader,
  relativeTime,
  Select,
  Separator,
  Table,
  TBody,
  TD,
  TH,
  THead,
  TR,
} from "./index";

describe("formatting", () => {
  it("uses Indian grouping for INR tenants", () => {
    expect(formatNumber(10000000, { currency: "INR" })).toBe("1,00,00,000");
    expect(formatNumber(10000000, { currency: "GBP" })).toBe("10,000,000");
  });

  it("formats minor units", () => {
    expect(formatMoneyMinor(48230000, "INR", { currency: "INR" })).toContain("4,82,300");
    expect(formatMoneyMinor(1999, "GBP")).toContain("19.99");
    expect(formatMoneyMinor(500, "JPY")).toContain("500");
  });

  it("formats dates in the tenant timezone", () => {
    const s = formatDateTime("2026-11-06T18:45:00Z", { timezone: "Asia/Kolkata", currency: "INR" });
    expect(s).toMatch(/7 Nov 2026/);
    expect(formatDateTime("2026-11-06T18:45:00Z")).toMatch(/6 Nov 2026/);
  });

  it("formats relative time", () => {
    const now = new Date("2026-11-06T12:00:00Z");
    expect(relativeTime("2026-11-06T11:58:00Z", now)).toBe("2 minutes ago");
    expect(relativeTime("2026-11-05T12:00:00Z", now)).toBe("yesterday");
    expect(relativeTime("2026-11-06T11:59:50Z", now)).toBe("10 seconds ago");
    expect(relativeTime("2026-11-06T14:00:00Z", now)).toBe("in 2 hours");
  });
});

describe("cn", () => {
  it("merges conflicting tailwind classes", () => {
    const hidden = Boolean(process.env.NEVER_SET_IN_TESTS);
    expect(cn("px-2", "px-4", hidden && "hidden")).toBe("px-4");
  });
});

describe("states", () => {
  it("renders empty state with next action", () => {
    render(<EmptyState title="No sources yet" description="Connect one" action={<Button>Add source</Button>} />);
    expect(screen.getByText("No sources yet")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add source" })).toBeInTheDocument();
  });

  it("renders error and forbidden states with defaults", () => {
    render(<ErrorState description="Try again" />);
    expect(screen.getByRole("alert")).toHaveTextContent("Something went wrong");
    render(<ForbiddenState />);
    expect(screen.getByText("You don't have access to this page")).toBeInTheDocument();
  });

  it("renders loading skeleton with accessible label", () => {
    render(<LoadingState rows={2} label="Loading team" />);
    expect(screen.getByRole("status", { name: "Loading team" })).toBeInTheDocument();
  });

  it("renders notices with roles by tone", () => {
    render(<Notice tone="danger">Bad</Notice>);
    expect(screen.getByRole("alert")).toHaveTextContent("Bad");
    render(<Notice>Info</Notice>);
    expect(screen.getAllByRole("status").at(-1)).toHaveTextContent("Info");
  });

  it("renders page header", () => {
    render(<PageHeader title="Team" description="Manage" actions={<Button>Invite</Button>} />);
    expect(screen.getByRole("heading", { name: "Team" })).toBeInTheDocument();
  });
});

describe("primitives", () => {
  it("renders the building blocks", () => {
    render(
      <Card>
        <CardHeader>
          <CardTitle>Title</CardTitle>
          <CardDescription>Desc</CardDescription>
        </CardHeader>
        <CardContent>
          <Badge tone="success">ok</Badge>
          <Field label="Email" htmlFor="email" hint="We never share it">
            <Input id="email" defaultValue="a@b.co" />
          </Field>
          <Select aria-label="role" defaultValue="viewer">
            <option value="viewer">Viewer</option>
          </Select>
          <Separator />
          <Button asChild variant="link">
            <a href="/x">Link</a>
          </Button>
          <Table>
            <THead>
              <TR>
                <TH>Name</TH>
              </TR>
            </THead>
            <TBody>
              <TR>
                <TD>Row</TD>
              </TR>
            </TBody>
          </Table>
        </CardContent>
      </Card>,
    );
    expect(screen.getByLabelText("Email")).toHaveValue("a@b.co");
    expect(screen.getByText("We never share it")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Link" })).toHaveAttribute("href", "/x");
    expect(screen.getByRole("columnheader", { name: "Name" })).toBeInTheDocument();
    expect(screen.getByText("ok")).toBeInTheDocument();
  });
});
