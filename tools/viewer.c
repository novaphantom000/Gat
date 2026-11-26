// offscreen checker for the asset pipeline: renders pngs into build/view/
#include <stdio.h>
#include <stdlib.h>
#include "game.h"
#include "rlgl.h"

static const char *vs_static =
    "#version 330\n"
    "in vec3 vertexPosition; in vec3 vertexNormal; in vec4 vertexColor;\n"
    "uniform mat4 mvp; uniform mat4 matModel;\n"
    "out vec3 n; out vec4 col;\n"
    "void main() { n = mat3(matModel) * vertexNormal; col = vertexColor; gl_Position = mvp * vec4(vertexPosition, 1.0); }\n";

static const char *vs_skin =
    "#version 330\n"
    "in vec3 vertexPosition; in vec3 vertexNormal; in vec4 vertexColor;\n"
    "in vec4 vertexBoneIndices; in vec4 vertexBoneWeights;\n"
    "uniform mat4 mvp; uniform mat4 matModel; uniform mat4 boneMatrices[32];\n"
    "out vec3 n; out vec4 col;\n"
    "void main() {\n"
    "  ivec4 id = ivec4(vertexBoneIndices + 0.5);\n"
    "  mat4 s = vertexBoneWeights.x * boneMatrices[id.x] + vertexBoneWeights.y * boneMatrices[id.y]\n"
    "         + vertexBoneWeights.z * boneMatrices[id.z] + vertexBoneWeights.w * boneMatrices[id.w];\n"
    "  n = mat3(matModel) * mat3(s) * vertexNormal; col = vertexColor;\n"
    "  gl_Position = mvp * s * vec4(vertexPosition, 1.0);\n"
    "}\n";

static const char *light =
    "float lit(vec3 nn) {\n"
    "  vec3 l = normalize(vec3(0.5, 0.8, -0.35));\n"
    "  return 0.38 + 0.2 * nn.y + 0.55 * max(dot(nn, l), 0.0);\n"
    "}\n";

static const char *fs_car =
    "#version 330\n"
    "in vec3 n; in vec4 col; uniform vec3 tint; out vec4 o;\n"
    "float lit(vec3 nn);\n"
    "void main() {\n"
    "  int m = int(col.a * 255.0 + 0.5); vec3 c = col.rgb; float e = 0.0;\n"
    "  if (m > 250) c *= tint;\n"
    "  else if (m == 192) e = 0.8;\n"
    "  else if (m == 64) { c = vec3(1.0, 0.95, 0.75); e = 0.5; }\n"
    "  else if (m == 32) { c = vec3(0.9, 0.05, 0.05); e = 0.5; }\n"
    "  o = vec4(c * lit(normalize(n)) + c * e, 1.0);\n"
    "}\n";

static const char *fs_char =
    "#version 330\n"
    "in vec3 n; in vec4 col; uniform vec3 pal[6]; out vec4 o;\n"
    "float lit(vec3 nn);\n"
    "void main() {\n"
    "  int r = int(col.r * 255.0 + 0.5);\n"
    "  o = vec4(pal[r] * (0.5 + 0.5 * col.g) * lit(normalize(n)), 1.0);\n"
    "}\n";

static Shader sh_car, sh_char, sh_skin;
static int loc_tint, loc_pal, loc_pal_skin, loc_bones;
static const char *cur_dir = "build/view";

static Shader load(const char *vs, const char *fs)
{
    char src[4096];
    snprintf(src, sizeof src, "%s%s", fs, light);
    return LoadShaderFromMemory(vs, src);
}

static void draw(Mesh m, Matrix xf, Shader s)
{
    Material mat = LoadMaterialDefault();
    mat.shader = s;
    DrawMesh(m, mat, xf);
}

static void draw_car(int i, Matrix xf, Color paint)
{
    CarModel *c = &car_models[i];
    float t[3] = { paint.r / 255.0f, paint.g / 255.0f, paint.b / 255.0f };
    SetShaderValue(sh_car, loc_tint, t, SHADER_UNIFORM_VEC3);
    draw(c->body, xf, sh_car);
    for (int k = 0; k < 4; k++) {
        Vector3 p = c->wheel_pos[k];
        draw(c->wheel, MatrixMultiply(MatrixTranslate(p.x, p.y, p.z), xf), sh_car);
    }
}

static void set_pal(Shader s, int loc, const Color *pal)
{
    float v[18];
    for (int i = 0; i < 6; i++) { v[i * 3] = pal[i].r / 255.0f; v[i * 3 + 1] = pal[i].g / 255.0f; v[i * 3 + 2] = pal[i].b / 255.0f; }
    SetShaderValueV(s, loc, v, SHADER_UNIFORM_VEC3, 6);
}

static const Color pal_a[R_COUNT] = { { 224, 172, 138, 255 }, { 40, 90, 190, 255 }, { 80, 84, 96, 255 }, { 25, 25, 28, 255 }, { 90, 55, 30, 255 }, { 245, 245, 245, 255 } };
static const Color pal_b[R_COUNT] = { { 150, 100, 70, 255 }, { 190, 60, 50, 255 }, { 50, 55, 70, 255 }, { 220, 220, 220, 255 }, { 230, 190, 80, 255 }, { 245, 245, 245, 255 } };

static void draw_ped(int body, int hair, Matrix xf, const Matrix *bones, const Color *pal)
{
    Shader s = bones ? sh_skin : sh_char;
    set_pal(s, bones ? loc_pal_skin : loc_pal, pal);
    if (bones) {
        rlEnableShader(s.id);
        rlSetUniformMatrices(loc_bones, bones, skel.count);
        rlDisableShader();
    }
    draw(body_mesh[body], xf, s);
    if (hair >= 0) {
        Color hp[R_COUNT];
        for (int i = 0; i < R_COUNT; i++) hp[i] = pal[i];
        if (hair == HAIR_CAP) { hp[R_SHIRT] = (Color){ 20, 30, 70, 255 }; hp[R_SHOES] = (Color){ 15, 15, 18, 255 }; }
        set_pal(s, bones ? loc_pal_skin : loc_pal, hp);
        draw(hair_mesh[hair], xf, s);
    }
}

static void shot(RenderTexture2D rt, const char *name)
{
    Image im = LoadImageFromTexture(rt.texture);
    ImageFlipVertical(&im);
    char path[256];
    snprintf(path, sizeof path, "%s/%s.png", cur_dir, name);
    ExportImage(im, path);
    UnloadImage(im);
    printf("wrote %s\n", path);
}

static void begin(RenderTexture2D rt, Camera3D cam)
{
    BeginTextureMode(rt);
    ClearBackground((Color){ 170, 190, 210, 255 });
    BeginMode3D(cam);
    DrawPlane((Vector3){ 0, -0.01f, 0 }, (Vector2){ 200, 200 }, (Color){ 90, 92, 96, 255 });
}

static void end(void) { EndMode3D(); EndTextureMode(); }

static void car_view(RenderTexture2D rt, const char *name, int first, int n, float yaw, Camera3D cam, bool grid)
{
    Color paints[CAR_MODELS] = { { 200, 40, 40, 255 }, { 40, 120, 220, 255 }, { 240, 200, 40, 255 }, { 60, 170, 90, 255 },
                                 { 170, 170, 175, 255 }, { 20, 20, 25, 255 }, { 230, 120, 30, 255 }, { 120, 60, 160, 255 },
                                 { 255, 255, 255, 255 }, { 255, 255, 255, 255 } };
    begin(rt, cam);
    for (int k = 0; k < n; k++) {
        int i = first + k;
        Vector3 p = grid ? (Vector3){ (k % 5 - 2) * 5.2f, 0, (k / 5) * 6.0f - 3.5f } : (Vector3){ (k - (n - 1) / 2.0f) * 6.0f, 0, 0 };
        draw_car(i, MatrixMultiply(MatrixRotateY(yaw), MatrixTranslate(p.x, p.y, p.z)), paints[i]);
    }
    end();
    shot(rt, name);
}

static void shot_cars(void)
{
    RenderTexture2D rt = LoadRenderTexture(1800, 1000);
    Camera3D cam = { { 0, 8, 22 }, { 0, 0.5f, 0 }, { 0, 1, 0 }, 40, CAMERA_PERSPECTIVE };
    car_view(rt, "cars_front", 0, 10, 0.62f, cam, true);
    car_view(rt, "cars_rear", 0, 10, 0.62f + PI, cam, true);
    cam = (Camera3D){ { 0, 1.8f, -40 }, { 0, 0.9f, 0 }, { 0, 1, 0 }, 24, CAMERA_PERSPECTIVE };
    car_view(rt, "cars_side_a", 0, 5, PI / 2, cam, false);
    car_view(rt, "cars_side_b", 5, 5, PI / 2, cam, false);
    cam = (Camera3D){ { 0, 34, -1 }, { 0, 0, 0 }, { 0, 0, 1 }, 40, CAMERA_PERSPECTIVE };
    car_view(rt, "cars_top", 0, 10, 0, cam, true);
    cam = (Camera3D){ { 0, 3.2f, 8.5f }, { 0, 0.8f, 0 }, { 0, 1, 0 }, 32, CAMERA_PERSPECTIVE };
    const int close[] = { CAR_SEDAN, CAR_PICKUP, CAR_COP, CAR_TAXI, CAR_OFFROAD, CAR_MINIVAN };
    for (int k = 0; k < 6; k++) {
        char name[32];
        snprintf(name, sizeof name, "car_close_%d", close[k]);
        car_view(rt, name, close[k], 1, k & 1 ? 2.6f : 0.55f, cam, false);
    }
    UnloadRenderTexture(rt);
}

static void shot_people(void)
{
    RenderTexture2D rt = LoadRenderTexture(1800, 760);
    Camera3D cam = { { 0, 1.5f, 9.5f }, { 0, 0.95f, 0 }, { 0, 1, 0 }, 30, CAMERA_PERSPECTIVE };
    int hairs[] = { HAIR_NONE, HAIR_BUZZ, HAIR_PARTED, HAIR_LONG, HAIR_BUNS, HAIR_BEARD, HAIR_CAP };
    for (int view = 0; view < 2; view++) {
        begin(rt, cam);
        for (int b = 0; b < 2; b++)
            for (int h = 0; h < 7; h++) {
                Matrix xf = MatrixMultiply(MatrixRotateY(view ? PI * 0.85f : 0.45f), MatrixTranslate((h - 3) * 1.3f, 0, b * 2.0f - 0.9f));
                draw_ped(b, hairs[h], xf, NULL, b ? pal_b : pal_a);
            }
        end();
        shot(rt, view ? "people_back" : "people_front");
    }
    UnloadRenderTexture(rt);
}

static void shot_heads(void)
{
    RenderTexture2D rt = LoadRenderTexture(1800, 460);
    int hairs[] = { HAIR_NONE, HAIR_BUZZ, HAIR_PARTED, HAIR_LONG, HAIR_BUNS, HAIR_BEARD, HAIR_CAP };
    const char *views[] = { "front", "34", "side", "back" };
    float yaw[] = { 0, 0.8f, PI / 2, PI };
    for (int b = 0; b < 2; b++)
        for (int view = 0; view < 4; view++) {
            Camera3D cam = { { 0, 1.7f, 3.4f }, { 0, 1.68f, 0 }, { 0, 1, 0 }, 16, CAMERA_PERSPECTIVE };
            begin(rt, cam);
            for (int h = 0; h < 7; h++)
                draw_ped(b, hairs[h], MatrixMultiply(MatrixRotateY(yaw[view]), MatrixTranslate((h - 3) * 0.4f, 0, 0)), NULL, b ? pal_b : pal_a);
            end();
            char name[32];
            snprintf(name, sizeof name, "heads_%c_%s", b ? 'f' : 'm', views[view]);
            shot(rt, name);
        }
    UnloadRenderTexture(rt);
}

static void shot_poses(void)
{
    RenderTexture2D rt = LoadRenderTexture(1800, 760);
    Camera3D cam = { { 0, 1.6f, 8.5f }, { 0, 0.9f, 0 }, { 0, 1, 0 }, 30, CAMERA_PERSPECTIVE };
    struct { int clip; float t; } sel[] = { { A_IDLE, 0.5f }, { A_WALK, 0.35f }, { A_SPRINT, 0.2f }, { A_PISTOL_AIM, 0.16f },
                                           { A_PUNCH_JAB, 0.35f }, { A_DRIVE, 0.5f }, { A_ROLL, 0.5f }, { A_DEATH, 1.2f } };
    for (int view = 0; view < 2; view++) {
        begin(rt, cam);
        for (int i = 0; i < 8; i++) {
            Quaternion rot[MAX_BONES];
            Matrix bones[MAX_BONES];
            Vector3 hips;
            pose_sample(&clips[sel[i].clip], sel[i].t, rot, &hips);
            pose_matrices(rot, hips, bones);
            Matrix xf = MatrixMultiply(MatrixRotateY(view ? PI * 0.5f : -0.4f), MatrixTranslate((3.5f - i) * 1.25f, 0, (i % 2) * 0.8f));
            draw_ped(i % 2, i % 5 == 0 ? HAIR_CAP : i % 5, xf, bones, i % 2 ? pal_b : pal_a);
            if (sel[i].clip == A_PISTOL_AIM) {
                Matrix hw = MatrixMultiply(MatrixInvert(skel.inv_bind[skel.hand_r]), bones[skel.hand_r]);
                Matrix grip = { -1, 0, 0, 0, 0, 0, 1, 0.07f, 0, 1, 0, 0, 0, 0, 0, 1 };
                Matrix g = MatrixMultiply(MatrixMultiply(grip, hw), xf);
                draw(gun_mesh[W_PISTOL], g, sh_car);
            }
        }
        end();
        shot(rt, view ? "poses_side" : "poses");
    }
    UnloadRenderTexture(rt);
}

static void shot_armed(void)
{
    RenderTexture2D rt = LoadRenderTexture(1500, 700);
    Matrix grip = { -1, 0, 0, 0, 0, 0, 1, 0.07f, 0, 1, 0, 0, 0, 0, 0, 1 };
    for (int view = 0; view < 2; view++) {
        Camera3D cam = { { 0, 1.5f, 6 }, { 0, 1.1f, 0 }, { 0, 1, 0 }, 28, CAMERA_PERSPECTIVE };
        begin(rt, cam);
        for (int i = 0; i < 3; i++) {
            Quaternion rot[MAX_BONES];
            Matrix bones[MAX_BONES];
            Vector3 hips;
            pose_sample(&clips[A_PISTOL_AIM], 0.16f, rot, &hips);
            pose_matrices(rot, hips, bones);
            Matrix xf = MatrixMultiply(MatrixRotateY(view ? 1.2f : -0.5f), MatrixTranslate((i - 1) * 1.6f, 0, 0));
            draw_ped(i & 1, HAIR_BUZZ + i, xf, bones, i & 1 ? pal_b : pal_a);
            Matrix hw = MatrixMultiply(MatrixInvert(skel.inv_bind[skel.hand_r]), bones[skel.hand_r]);
            draw(gun_mesh[W_PISTOL + i], MatrixMultiply(MatrixMultiply(grip, hw), xf), sh_car);
        }
        end();
        shot(rt, view ? "armed_side" : "armed");
    }
    UnloadRenderTexture(rt);
}

static void shot_bind(void)
{
    RenderTexture2D rt = LoadRenderTexture(900, 760);
    Camera3D cam = { { 0, 1.3f, 5.5f }, { 0, 0.9f, 0 }, { 0, 1, 0 }, 40, CAMERA_PERSPECTIVE };
    begin(rt, cam);
    Matrix bones[MAX_BONES];
    Quaternion rot[MAX_BONES];
    for (int i = 0; i < skel.count; i++) rot[i] = skel.bind_rot[i];
    pose_matrices(rot, skel.bind_pos[skel.hips], bones);
    draw_ped(0, HAIR_BUZZ, MatrixTranslate(-0.8f, 0, 0), bones, pal_a);
    draw_ped(1, HAIR_LONG, MatrixTranslate(0.8f, 0, 0), bones, pal_b);
    end();
    shot(rt, "bind");
    UnloadRenderTexture(rt);
}

static void shot_guns(void)
{
    RenderTexture2D rt = LoadRenderTexture(1500, 600);
    float dist[] = { 0, 0.7f, 1.0f, 2.0f };
    for (int i = W_PISTOL; i < W_COUNT; i++) {
        for (int side = 0; side < 2; side++) {
            Camera3D cam = { { side ? 0.6f * dist[i] : dist[i], 0.1f * dist[i], side ? -dist[i] : 0.2f * dist[i] }, { 0, 0, 0.12f * dist[i] }, { 0, 1, 0 }, 30, CAMERA_PERSPECTIVE };
            begin(rt, cam);
            draw(gun_mesh[i], MatrixIdentity(), sh_car);
            rlDisableDepthTest();
            DrawSphere((Vector3){ 0, 0, 0 }, 0.008f * dist[i], RED);
            rlEnableDepthTest();
            end();
            char name[32];
            snprintf(name, sizeof name, "gun_%d_%s", i, side ? "34" : "side");
            shot(rt, name);
        }
    }
    UnloadRenderTexture(rt);
}

int main(void)
{
    SetConfigFlags(FLAG_WINDOW_HIDDEN | FLAG_MSAA_4X_HINT);
    SetTraceLogLevel(LOG_WARNING);
    InitWindow(1800, 1000, "viewer");
    assets_load();
    sh_car = load(vs_static, fs_car);
    sh_char = load(vs_static, fs_char);
    sh_skin = load(vs_skin, fs_char);
    loc_tint = GetShaderLocation(sh_car, "tint");
    loc_pal = GetShaderLocation(sh_char, "pal");
    loc_pal_skin = GetShaderLocation(sh_skin, "pal");
    loc_bones = GetShaderLocation(sh_skin, "boneMatrices");
    shot_cars();
    shot_people();
    shot_bind();
    shot_heads();
    shot_poses();
    shot_guns();
    shot_armed();
    CloseWindow();
    return 0;
}
