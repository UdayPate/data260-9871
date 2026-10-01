// HW5 Part 1.III.1 + 1.III.2: the Redux Toolkit slice for the primary
// domain entity (fixtures), plus the four async thunks that call the
// FastAPI endpoints with axios.
//
// The reducers are deliberately the only place fixture state changes, so the
// Home screen re-renders automatically after a create, update or delete -
// no manual list refetch anywhere in the UI.
import { createSlice, createAsyncThunk } from "@reduxjs/toolkit";

import { http, errorMessage } from "./api";

export const fetchFixtures = createAsyncThunk(
  "fixtures/fetchAll",
  async (_arg, { rejectWithValue }) => {
    try {
      const response = await http.get("/fixtures");
      return response.data;
    } catch (err) {
      return rejectWithValue(errorMessage(err));
    }
  }
);

export const createFixture = createAsyncThunk(
  "fixtures/create",
  async (fixture, { rejectWithValue }) => {
    try {
      const response = await http.post("/fixtures", fixture);
      return response.data;
    } catch (err) {
      return rejectWithValue(errorMessage(err));
    }
  }
);

export const updateFixture = createAsyncThunk(
  "fixtures/update",
  async ({ id, changes }, { rejectWithValue }) => {
    try {
      const response = await http.put(`/fixtures/${id}`, changes);
      return response.data;
    } catch (err) {
      return rejectWithValue(errorMessage(err));
    }
  }
);

export const deleteFixture = createAsyncThunk(
  "fixtures/delete",
  async (id, { rejectWithValue }) => {
    try {
      await http.delete(`/fixtures/${id}`);
      // The reducer needs the id to drop the row; the API body only says
      // {success, deleted_id}, so the id is returned explicitly here.
      return Number(id);
    } catch (err) {
      return rejectWithValue(errorMessage(err));
    }
  }
);

const initialState = {
  items: [],
  status: "idle", // idle | loading | succeeded | failed
  error: null,
  lastAction: null,   // short confirmation shown on the Home screen
  lastTouchedId: null, // the record just created or updated, so the Home
                       // screen can open on the page holding it
};

const fixturesSlice = createSlice({
  name: "fixtures",
  initialState,
  reducers: {
    clearFixtureFeedback(state) {
      state.error = null;
      state.lastAction = null;
      state.lastTouchedId = null;
    },
  },
  extraReducers: (builder) => {
    builder
      // ---- fetch ----
      .addCase(fetchFixtures.pending, (state) => {
        state.status = "loading";
        state.error = null;
      })
      .addCase(fetchFixtures.fulfilled, (state, action) => {
        state.status = "succeeded";
        state.items = action.payload;
      })
      .addCase(fetchFixtures.rejected, (state, action) => {
        state.status = "failed";
        state.error = action.payload || "Could not load fixtures";
      })

      // ---- create: append, so the Home list grows without a refetch ----
      .addCase(createFixture.fulfilled, (state, action) => {
        state.items.push(action.payload);
        state.error = null;
        state.lastTouchedId = action.payload.id;
        state.lastAction = `Created fixture #${action.payload.id} (${action.payload.fixture_code})`;
      })
      .addCase(createFixture.rejected, (state, action) => {
        state.error = action.payload || "Could not create fixture";
      })

      // ---- update: replace in place ----
      .addCase(updateFixture.fulfilled, (state, action) => {
        const i = state.items.findIndex((f) => f.id === action.payload.id);
        if (i !== -1) state.items[i] = action.payload;
        state.error = null;
        state.lastTouchedId = action.payload.id;
        state.lastAction = `Updated fixture #${action.payload.id}`;
      })
      .addCase(updateFixture.rejected, (state, action) => {
        state.error = action.payload || "Could not update fixture";
      })

      // ---- delete: remove from state ----
      .addCase(deleteFixture.fulfilled, (state, action) => {
        state.items = state.items.filter((f) => f.id !== action.payload);
        state.error = null;
        state.lastTouchedId = null;
        state.lastAction = `Deleted fixture #${action.payload}`;
      })
      .addCase(deleteFixture.rejected, (state, action) => {
        state.error = action.payload || "Could not delete fixture";
      });
  },
});

export const { clearFixtureFeedback } = fixturesSlice.actions;

export const selectFixtures = (state) => state.fixtures.items;
export const selectFixturesStatus = (state) => state.fixtures.status;
export const selectFixturesError = (state) => state.fixtures.error;
export const selectLastAction = (state) => state.fixtures.lastAction;
export const selectLastTouchedId = (state) => state.fixtures.lastTouchedId;
export const selectFixtureById = (state, id) =>
  state.fixtures.items.find((f) => f.id === Number(id));

export default fixturesSlice.reducer;
