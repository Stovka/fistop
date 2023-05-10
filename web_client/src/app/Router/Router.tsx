import * as React from "react";
import { Routes } from "react-router-dom";

import { GetRoutes } from "../Router/Routes";

const AppRoutes = (): React.ReactElement => (
    <Routes>{GetRoutes()}</Routes>
);

export default AppRoutes;
