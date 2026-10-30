// A small JSON reader (the radio and podcast directories answer in JSON).
#pragma once
#include <string>
#include <vector>
#include <map>
#include <memory>
#include <cstdlib>

struct Json {
    enum Kind { Null, Bool, Number, String, Array, Object } kind = Null;
    bool b = false;
    double num = 0;
    std::string str;                       // UTF-8
    std::vector<Json> arr;
    std::vector<std::pair<std::string, Json>> obj;

    const Json &operator[](const char *key) const {
        static Json none;
        if (kind != Object) return none;
        for (auto &kv : obj) if (kv.first == key) return kv.second;
        return none;
    }
    const Json &operator[](size_t i) const {
        static Json none;
        return kind == Array && i < arr.size() ? arr[i] : none;
    }
    size_t size() const { return kind == Array ? arr.size() : kind == Object ? obj.size() : 0; }
    std::string s() const {
        if (kind == String) return str;
        if (kind == Number) {
            char buf[64];
            if (num == (long long)num) snprintf(buf, sizeof buf, "%lld", (long long)num);
            else snprintf(buf, sizeof buf, "%g", num);
            return buf;
        }
        if (kind == Bool) return b ? "true" : "false";
        return "";
    }
    double n() const { return kind == Number ? num : kind == String ? atof(str.c_str()) : 0; }
};

class JsonParser {
    const char *p, *end;
    void ws() { while (p < end && (*p == ' ' || *p == '\t' || *p == '\n' || *p == '\r')) p++; }
    static void put_utf8(std::string &o, unsigned cp) {
        if (cp < 0x80) o += (char)cp;
        else if (cp < 0x800) { o += (char)(0xC0 | (cp >> 6)); o += (char)(0x80 | (cp & 0x3F)); }
        else if (cp < 0x10000) { o += (char)(0xE0 | (cp >> 12)); o += (char)(0x80 | ((cp >> 6) & 0x3F)); o += (char)(0x80 | (cp & 0x3F)); }
        else { o += (char)(0xF0 | (cp >> 18)); o += (char)(0x80 | ((cp >> 12) & 0x3F)); o += (char)(0x80 | ((cp >> 6) & 0x3F)); o += (char)(0x80 | (cp & 0x3F)); }
    }
    unsigned hex4() {
        unsigned v = 0;
        for (int i = 0; i < 4 && p < end; i++, p++) {
            char c = *p;
            v = v * 16 + (c >= '0' && c <= '9' ? c - '0' : c >= 'a' && c <= 'f' ? c - 'a' + 10 : c >= 'A' && c <= 'F' ? c - 'A' + 10 : 0);
        }
        return v;
    }
    bool string(std::string &o) {
        if (p >= end || *p != '"') return false;
        p++;
        while (p < end && *p != '"') {
            if (*p == '\\' && p + 1 < end) {
                p++;
                char c = *p++;
                switch (c) {
                    case 'n': o += '\n'; break;
                    case 't': o += '\t'; break;
                    case 'r': o += '\r'; break;
                    case 'b': o += '\b'; break;
                    case 'f': o += '\f'; break;
                    case 'u': {
                        unsigned cp = hex4();
                        if (cp >= 0xD800 && cp < 0xDC00 && p + 1 < end && p[0] == '\\' && p[1] == 'u') {
                            p += 2;
                            unsigned lo = hex4();
                            cp = 0x10000 + ((cp - 0xD800) << 10) + (lo - 0xDC00);
                        }
                        put_utf8(o, cp);
                        break;
                    }
                    default: o += c;
                }
            } else o += *p++;
        }
        if (p < end) p++;
        return true;
    }
    bool value(Json &v, int depth) {
        if (depth > 200) return false;
        ws();
        if (p >= end) return false;
        char c = *p;
        if (c == '{') {
            v.kind = Json::Object;
            p++;
            ws();
            if (p < end && *p == '}') { p++; return true; }
            while (p < end) {
                ws();
                std::string k;
                if (!string(k)) return false;
                ws();
                if (p >= end || *p != ':') return false;
                p++;
                Json x;
                if (!value(x, depth + 1)) return false;
                v.obj.emplace_back(std::move(k), std::move(x));
                ws();
                if (p < end && *p == ',') { p++; continue; }
                if (p < end && *p == '}') { p++; return true; }
                return false;
            }
            return false;
        }
        if (c == '[') {
            v.kind = Json::Array;
            p++;
            ws();
            if (p < end && *p == ']') { p++; return true; }
            while (p < end) {
                Json x;
                if (!value(x, depth + 1)) return false;
                v.arr.push_back(std::move(x));
                ws();
                if (p < end && *p == ',') { p++; continue; }
                if (p < end && *p == ']') { p++; return true; }
                return false;
            }
            return false;
        }
        if (c == '"') { v.kind = Json::String; return string(v.str); }
        if (c == 't' && end - p >= 4) { v.kind = Json::Bool; v.b = true; p += 4; return true; }
        if (c == 'f' && end - p >= 5) { v.kind = Json::Bool; v.b = false; p += 5; return true; }
        if (c == 'n' && end - p >= 4) { v.kind = Json::Null; p += 4; return true; }
        char *e = nullptr;
        std::string num(p, std::min<size_t>(end - p, 64));
        v.num = strtod(num.c_str(), &e);
        if (e == num.c_str()) return false;
        v.kind = Json::Number;
        p += e - num.c_str();
        return true;
    }

public:
    static bool parse(const std::string &text, Json &out) {
        JsonParser j;
        j.p = text.data();
        j.end = text.data() + text.size();
        return j.value(out, 0);
    }
};
