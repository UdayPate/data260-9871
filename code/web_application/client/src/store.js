// HW5 Part 1.III.1: the Redux Toolkit store.
import { configureStore } from "@reduxjs/toolkit";

import fixturesReducer from "./fixturesSlice";
import teamsReducer from "./teamsSlice";

export const store = configureStore({
  reducer: {
    fixtures: fixturesReducer,
    teams: teamsReducer,
  },
});
