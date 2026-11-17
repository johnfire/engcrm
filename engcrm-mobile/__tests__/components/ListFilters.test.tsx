import { fireEvent, render } from "@testing-library/react-native";
import { Text } from "react-native";

import { FilterPanel, ListSearchRow } from "../../components/ListFilters";

const rowProps = {
  placeholder: "Search",
  search: "",
  onSearchChange: jest.fn(),
  onSubmit: jest.fn(),
  onToggleFilters: jest.fn(),
};

describe("ListSearchRow", () => {
  it("names the Filters button plainly when nothing narrows the list", () => {
    const screen = render(<ListSearchRow {...rowProps} filtersOpen={false} activeFilters={0} />);
    const button = screen.getByLabelText("Filters");
    expect(button.props.accessibilityState).toEqual({ expanded: false });
    expect(screen.getByText("Filters ▾")).toBeTruthy();
  });

  it("counts the filters in use, so a narrowed list is never mistaken for everything", () => {
    const screen = render(<ListSearchRow {...rowProps} filtersOpen activeFilters={2} />);
    expect(screen.getByText("Filters (2) ▴")).toBeTruthy();
    expect(screen.getByLabelText("Filters (2)").props.accessibilityState).toEqual({ expanded: true });
  });

  it("opens and closes the filters and keeps search and its action on screen", () => {
    const onToggleFilters = jest.fn();
    const onSearchChange = jest.fn();
    const screen = render(
      <ListSearchRow {...rowProps} onToggleFilters={onToggleFilters} onSearchChange={onSearchChange}
        filtersOpen={false} activeFilters={0} action={<Text>Add</Text>} />,
    );
    fireEvent.press(screen.getByLabelText("Filters"));
    expect(onToggleFilters).toHaveBeenCalledTimes(1);
    fireEvent.changeText(screen.getByLabelText("Search"), "Café");
    expect(onSearchChange).toHaveBeenCalledWith("Café");
    expect(screen.getByText("Add")).toBeTruthy();
  });
});

describe("FilterPanel", () => {
  it("shows nothing while closed", () => {
    const screen = render(
      <FilterPanel open={false} activeFilters={1} onClear={jest.fn()}>
        <Text>Stage chips</Text>
      </FilterPanel>,
    );
    expect(screen.queryByText("Stage chips")).toBeNull();
    expect(screen.queryByText("Clear filters")).toBeNull();
  });

  it("shows its filters when open, and Clear only when a filter is in use", () => {
    const onClear = jest.fn();
    const screen = render(
      <FilterPanel open activeFilters={1} onClear={onClear}>
        <Text>Stage chips</Text>
      </FilterPanel>,
    );
    expect(screen.getByText("Stage chips")).toBeTruthy();
    fireEvent.press(screen.getByText("Clear filters"));
    expect(onClear).toHaveBeenCalledTimes(1);

    screen.rerender(
      <FilterPanel open activeFilters={0} onClear={onClear}>
        <Text>Stage chips</Text>
      </FilterPanel>,
    );
    expect(screen.queryByText("Clear filters")).toBeNull();
  });
});
