import axios from "axios";
import * as https from "node:https";

const orders = axios.create({baseURL: process.env.ORDERS_API});
orders.get("/orders/42");

fetch("https://identity.example/oauth/keys");
https.request({hostname: "audit.example", path: "/events", method: "POST"});
