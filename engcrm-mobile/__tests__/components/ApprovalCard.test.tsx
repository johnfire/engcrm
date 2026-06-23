import React from "react";
import { render, fireEvent } from "@testing-library/react-native";
import { ApprovalCard } from "../../components/ApprovalCard";
import { Approval } from "../../services/api";

jest.mock("expo-secure-store", () => ({
  getItemAsync: jest.fn(),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));

const mockApproval: Approval = {
  id: 1,
  draft_subject: "Test Subject",
  draft_body: "Hello World body text",
  created_at: "2026-06-01T10:00:00Z",
  contact_id: 42,
  name: "Galerie Test",
  city: "München",
  email: "test@galerie.de",
  website: "https://galerie-test.de",
};

describe("ApprovalCard", () => {
  it("renders venue name and subject", () => {
    const { getByText } = render(
      <ApprovalCard
        item={mockApproval}
        onApprove={jest.fn()}
        onReject={jest.fn()}
        onEdit={jest.fn()}
      />,
    );
    expect(getByText("Galerie Test, München")).toBeTruthy();
    expect(getByText("Test Subject")).toBeTruthy();
  });

  it("calls onApprove when Approve tapped", () => {
    const onApprove = jest.fn();
    const { getByText } = render(
      <ApprovalCard
        item={mockApproval}
        onApprove={onApprove}
        onReject={jest.fn()}
        onEdit={jest.fn()}
      />,
    );
    fireEvent.press(getByText("Approve"));
    expect(onApprove).toHaveBeenCalledWith(1);
  });

  it("calls onReject when Reject tapped", () => {
    const onReject = jest.fn();
    const { getByText } = render(
      <ApprovalCard
        item={mockApproval}
        onApprove={jest.fn()}
        onReject={onReject}
        onEdit={jest.fn()}
      />,
    );
    fireEvent.press(getByText("Reject"));
    expect(onReject).toHaveBeenCalledWith(mockApproval);
  });
});
