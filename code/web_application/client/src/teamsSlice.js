// HW5 Part 1.III: a small second slice holding the related entity.
//
// The assignment only requires a slice for the primary domain entity, but a
// fixture cannot be created without a valid home_team_id, so the create and
// update forms need the list of teams to populate their dropdown. Keeping
// that in its own slice is tidier than parking unrelated data in
// fixturesSlice. Only a read thunk is needed here - team CRUD is exercised
// through the API in Part 1.II.
import { createSlice, createAsyncThunk } from "@reduxjs/toolkit";

import { http, errorMessage } from "./api";

export const fetchTeams = createAsyncThunk(
  "teams/fetchAll",
  async (_arg, { rejectWithValue }) => {
    try {
      // page_size is capped at 100 by the API; the league has 12 teams.
      const response = await http.get("/teams", {
        params: { page: 1, page_size: 100 },
      });
      return response.data.items;
    } catch (err) {
      return rejectWithValue(errorMessage(err));
    }
  }
);

const teamsSlice = createSlice({
  name: "teams",
  initialState: { items: [], status: "idle", error: null },
  reducers: {},
  extraReducers: (builder) => {
    builder
      .addCase(fetchTeams.pending, (state) => {
        state.status = "loading";
      })
      .addCase(fetchTeams.fulfilled, (state, action) => {
        state.status = "succeeded";
        state.items = action.payload;
      })
      .addCase(fetchTeams.rejected, (state, action) => {
        state.status = "failed";
        state.error = action.payload || "Could not load teams";
      });
  },
});

export const selectTeams = (state) => state.teams.items;

export default teamsSlice.reducer;
