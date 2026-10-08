// Calibração (08/10/2026): a ponte com o Tekla Structures aberto, pela Open API (.NET Framework 4.8).
// Compila com o csc do Windows (compilar.ps1) e roda com o modelo aberto no Tekla:
//
//   TeklaPonte.exe perfis                      a sintaxe dos perfis paramétricos do catálogo do Tekla
//   TeklaPonte.exe sondar <perfil>...          cria uma viga de teste por perfil, lê o eixo, a caixa e as propriedades, apaga
//   TeklaPonte.exe criar <entrada.json>        cria as peças (apaga antes as que levam o nome de calibração)
//   TeklaPonte.exe ler <saida.json>            lê as peças de calibração: perfil, comprimento, peso, área, propriedades
//   TeklaPonte.exe limpar                      apaga as peças de calibração
//
// As peças criadas levam o comentário "CALIBRACAO-METALICA" (o UserProperty COMMENT) para serem achadas e apagadas.
using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text;
using System.Web.Script.Serialization;
using Tekla.Structures.Geometry3d;
using Tekla.Structures.Model;
using Tekla.Structures.Catalogs;
using Tekla.Structures.Analysis;

public static class TeklaPonte
{
    const string MARCA = "CALIBRACAO-METALICA";
    static readonly string[] PASTAS = {
        @"C:\Program Files\Tekla Structures\2026.0\bin\Net48Runtime",
        @"C:\Program Files\Tekla Structures\2026.0\bin" };

    public static int Main(string[] args)
    {
        AppDomain.CurrentDomain.AssemblyResolve += (s, e) =>
        {
            string nome = new AssemblyName(e.Name).Name + ".dll";
            foreach (string d in PASTAS)
            {
                string p = Path.Combine(d, nome);
                if (File.Exists(p)) return System.Reflection.Assembly.LoadFrom(p);
            }
            return null;
        };
        Console.OutputEncoding = Encoding.UTF8;
        try { return Rodar(args); }
        catch (Exception ex) { Console.WriteLine("ERRO: " + ex); return 2; }
    }

    static int Rodar(string[] args)
    {
        if (args.Length == 0) { Console.WriteLine("comandos: perfis | sondar <perfil>... | criar <json> | ler <json> | limpar"); return 1; }
        Model m = new Model();
        if (!m.GetConnectionStatus()) { Console.WriteLine("ERRO: o Tekla não está com um modelo aberto"); return 3; }
        switch (args[0])
        {
            case "perfis": return Perfis();
            case "materiais": return Materiais();
            case "sondar": return Sondar(m, args.Skip(1).ToArray());
            case "criar": return Criar(m, args[1]);
            case "ler": return Ler(m, args[1]);
            case "limpar": Console.WriteLine("apagadas: " + Limpar(m)); return 0;
            case "analise": return Analise(m, args[1], args.Length > 2 ? args[2] : "NEUTRAL_AXIS");
        }
        Console.WriteLine("comando desconhecido: " + args[0]);
        return 1;
    }

    // ---------------------------------------------------------------- catálogo
    static int Perfis()
    {
        CatalogHandler ch = new CatalogHandler();
        if (!ch.GetConnectionStatus()) { Console.WriteLine("ERRO: catálogo sem conexão"); return 3; }
        ProfileItemEnumerator en = ch.GetParametricProfileItems();
        while (en.MoveNext())
        {
            ParametricProfileItem it = en.Current as ParametricProfileItem;
            if (it == null) continue;
            var ps = new List<string>();
            foreach (ProfileItemParameter p in it.aProfileItemParameters) ps.Add(p.Property + "=" + p.Value);
            Console.WriteLine(it.ProfilePrefix + " | " + it.ParameterString + " | " + string.Join(", ", ps));
        }
        return 0;
    }

    static int Materiais()
    {
        CatalogHandler ch = new CatalogHandler();
        MaterialItemEnumerator en = ch.GetMaterialItems();
        while (en.MoveNext())
        {
            MaterialItem it = en.Current;
            Console.WriteLine(it.MaterialName + " | " + it.Type + " | densidade " + it.ProfileDensity + " / " + it.PlateDensity +
                              " | E " + it.ModulusOfElasticity);
        }
        return 0;
    }

    // ---------------------------------------------------------------- sondagem
    static double Rp(Part p, string nome)
    {
        double v = 0.0;
        p.GetReportProperty(nome, ref v);
        return v;
    }

    static int Sondar(Model m, string[] perfis)
    {
        double y = 0;
        foreach (string perfil in perfis)
        {
            foreach (bool vertical in new[] { false, true })
            {
                Beam b = new Beam();
                b.StartPoint = new Point(0, y, 0);
                b.EndPoint = vertical ? new Point(0, y, 1000) : new Point(1000, y, 0);
                b.Profile.ProfileString = perfil;
                b.Material.MaterialString = "STEEL_UNDEFINED";
                b.Position.Plane = Position.PlaneEnum.MIDDLE;
                b.Position.Depth = Position.DepthEnum.MIDDLE;
                b.Position.Rotation = Position.RotationEnum.FRONT;
                b.Name = "SONDA";
                if (!b.Insert()) { Console.WriteLine(perfil + ": o Tekla recusou o perfil"); break; }
                CoordinateSystem cs = b.GetCoordinateSystem();
                Solid so = b.GetSolid();
                Vector ax = cs.AxisX.GetNormal(), ay = cs.AxisY.GetNormal();
                Console.WriteLine(string.Format("{0} {1}: eixo X ({2:F2},{3:F2},{4:F2}) eixo Y ({5:F2},{6:F2},{7:F2}) caixa ({8:F1},{9:F1},{10:F1})..({11:F1},{12:F1},{13:F1})",
                    perfil, vertical ? "vertical" : "horizontal", ax.X, ax.Y, ax.Z, ay.X, ay.Y, ay.Z,
                    so.MinimumPoint.X, so.MinimumPoint.Y - y, so.MinimumPoint.Z, so.MaximumPoint.X, so.MaximumPoint.Y - y, so.MaximumPoint.Z));
                if (!vertical)
                    Console.WriteLine(string.Format("   kg/m {0:F3}  A {1:F1} mm²  Iy {2:F0}  Iz {3:F0}  J {4:F1} mm⁴  Wy {5:F0}  Wz {6:F0}  área de pintura {7:F4} m²/m",
                        Rp(b, "PROFILE.WEIGHT_PER_UNIT_LENGTH"), Rp(b, "PROFILE.CROSS_SECTION_AREA"), Rp(b, "PROFILE.MOMENT_OF_INERTIA_Y"),
                        Rp(b, "PROFILE.MOMENT_OF_INERTIA_Z"), Rp(b, "PROFILE.TORSIONAL_CONSTANT_X"), Rp(b, "PROFILE.SECTION_MODULUS_Y"),
                        Rp(b, "PROFILE.SECTION_MODULUS_Z"), Rp(b, "PROFILE.COVER_AREA") / 1000.0));
                b.Delete();
            }
            y += 1000;
        }
        m.CommitChanges();
        return 0;
    }

    // ---------------------------------------------------------------- criar e ler
    static int Limpar(Model m)
    {
        int n = 0;
        ModelObjectEnumerator en = m.GetModelObjectSelector().GetAllObjectsWithType(ModelObject.ModelObjectEnum.BEAM);
        var apagar = new List<Beam>();
        while (en.MoveNext())
        {
            Beam b = en.Current as Beam;
            if (b == null) continue;
            string c = "";
            b.GetUserProperty("comment", ref c);
            if (c == MARCA || b.Name == "SONDA") apagar.Add(b);
        }
        foreach (Beam b in apagar) if (b.Delete()) n++;
        m.CommitChanges();
        return n;
    }

    static double D(object o) { return Convert.ToDouble(o, System.Globalization.CultureInfo.InvariantCulture); }

    static Point Pt(object o)
    {
        var l = (IList)o;
        return new Point(D(l[0]), D(l[1]), D(l[2]));
    }

    static Vector Vt(object o)
    {
        var l = (IList)o;
        return new Vector(D(l[0]), D(l[1]), D(l[2]));
    }

    static double Dot(Vector a, Vector b) { return a.X * b.X + a.Y * b.Y + a.Z * b.Z; }

    // o centro de gravidade da peça visto da linha a–b, nos eixos u e v da seção (mm)
    static double[] CgNaSecao(Beam b, Point a, Vector u, Vector v)
    {
        double x = 0, y = 0, z = 0;
        b.GetReportProperty("COG_X", ref x);
        b.GetReportProperty("COG_Y", ref y);
        b.GetReportProperty("COG_Z", ref z);
        var d = new Vector(x - a.X, y - a.Y, z - a.Z);
        return new[] { Dot(d, u), Dot(d, v) };
    }

    static int Criar(Model m, string arquivo)
    {
        var js = new JavaScriptSerializer { MaxJsonLength = int.MaxValue };
        var dados = (Dictionary<string, object>)js.DeserializeObject(File.ReadAllText(arquivo, Encoding.UTF8));
        Console.WriteLine("apagadas antes: " + Limpar(m));
        int ok = 0, falhou = 0;
        double piorCg = 0;
        var relatorio = new List<Dictionary<string, object>>();
        foreach (Dictionary<string, object> p in (object[])dados["pecas"])
        {
            Point a = Pt(p["inicio"]), z = Pt(p["fim"]);
            Vector u = Vt(p["u"]), v = Vt(p["v"]);
            var cc = (IList)p["caixa_cg"];
            double cu = D(cc[0]), cv = D(cc[1]);
            Beam b = new Beam();
            b.StartPoint = a;
            b.EndPoint = z;
            b.Profile.ProfileString = (string)p["perfil"];
            b.Material.MaterialString = p.ContainsKey("material") ? (string)p["material"] : "STEEL_UNDEFINED";
            b.Name = (string)p["nome"];
            b.Class = "1";
            b.Position.Plane = Position.PlaneEnum.MIDDLE;
            b.Position.Depth = Position.DepthEnum.MIDDLE;
            b.Position.Rotation = Position.RotationEnum.FRONT;
            b.PartNumber.Prefix = p.ContainsKey("prefixo") ? (string)p["prefixo"] : "P";
            if (!b.Insert()) { falhou++; Console.WriteLine("recusada: " + p["id"] + " " + p["perfil"]); continue; }
            // o giro: o ângulo entre o eixo Y que o Tekla deu e a nossa altura v; o sinal da convenção e o quadrante pelo
            // centro de gravidade (no Tekla, centrado pela caixa, ele fica a -c da linha)
            CoordinateSystem cs = b.GetCoordinateSystem();
            Vector ex = cs.AxisX.GetNormal(), ey = cs.AxisY.GetNormal();
            double th0 = Math.Atan2(Dot(ey.Cross(v), ex), Dot(ey, v)) * 180.0 / Math.PI;
            double melhor = double.MaxValue, giro = 0;
            foreach (double s in new[] { 1.0, -1.0 })
                for (int k = 0; k < 4; k++)
                {
                    double g = s * th0 + 90.0 * k;
                    b.Position.RotationOffset = g;
                    b.Modify();
                    double[] cg = CgNaSecao(b, a, u, v);
                    double err = Math.Sqrt(Math.Pow(cg[0] + cu, 2) + Math.Pow(cg[1] + cv, 2));
                    if (err < melhor) { melhor = err; giro = g; }
                }
            b.Position.RotationOffset = giro;
            // a linha do Tekla (o centro da caixa) sai do nosso centro de gravidade em +c
            var desl = new Vector(cu * u.X + cv * v.X, cu * u.Y + cv * v.Y, cu * u.Z + cv * v.Z);
            b.StartPoint = new Point(a.X + desl.X, a.Y + desl.Y, a.Z + desl.Z);
            b.EndPoint = new Point(z.X + desl.X, z.Y + desl.Y, z.Z + desl.Z);
            b.Modify();
            double[] fim = CgNaSecao(b, a, u, v);
            double erro = Math.Sqrt(fim[0] * fim[0] + fim[1] * fim[1]);
            piorCg = Math.Max(piorCg, erro);
            b.SetUserProperty("comment", MARCA);
            b.SetUserProperty("USER_FIELD_1", (string)p["id"]);
            b.Modify();
            relatorio.Add(new Dictionary<string, object> { { "id", p["id"] }, { "giro", giro }, { "cg_fora_mm", Math.Round(erro, 2) } });
            ok++;
            if (ok % 50 == 0) Console.WriteLine("  " + ok + " peças…");
        }
        m.CommitChanges();
        File.WriteAllText(Path.ChangeExtension(arquivo, ".criadas.json"), js.Serialize(relatorio), new UTF8Encoding(false));
        Console.WriteLine(string.Format("criadas {0}, recusadas {1}; o centro de gravidade do Tekla a até {2:F2} mm da nossa linha", ok, falhou, piorCg));
        return falhou == 0 ? 0 : 4;
    }

    // ---------------------------------------------------------------- o modelo de cálculo do Tekla
    static double[] V3(Vector v) { return v == null ? null : new[] { v.X, v.Y, v.Z }; }

    static Dictionary<string, object> Ponta(AnalysisBeamEnd e)
    {
        var d = new Dictionary<string, object>();
        if (e == null) return d;
        d["excentricidade"] = V3(e.Eccentricity);
        if (e.Connectivity != null)
        {
            d["ligacao"] = e.Connectivity.Connectivity == null ? null : e.Connectivity.Connectivity.Select(c => c.ToString().Replace("CONNECTIVITY_", "")).ToArray();
            d["molas"] = e.Connectivity.Spring;
        }
        return d;
    }

    static Dictionary<string, object> Secao(AnalysisCrossSection s)
    {
        if (s == null) return null;
        return new Dictionary<string, object> { { "nome", s.Name }, { "A", s.A }, { "Iyy", s.Iyy }, { "Izz", s.Izz }, { "It", s.It },
                                                { "Iy", s.Iy }, { "Iz", s.Iz }, { "Iw", s.Iw }, { "Wyy", s.Wyy }, { "Wzz", s.Wzz }, { "calculado", s.Calculated } };
    }

    static int Analise(Model m, string saida, string eixo)
    {
        AnalysisModel am = new AnalysisModel();
        am.AnalysisModelName = "CALIBRACAO-" + eixo;
        try
        {
            am.Select();
            if (am.ID != null && am.ID.ID > 0) { Console.WriteLine("apagando o modelo de cálculo anterior " + am.AnalysisModelName); am.Delete(); }
        }
        catch (Exception) { }
        am = new AnalysisModel();
        am.AnalysisModelName = "CALIBRACAO-" + eixo;
        am.ConstructionMethod = AnalysisModel.ConstructionMethodEnum.SELECTED_PARTS;
        am.MemberAxislocation = (AnalysisModel.AxisLocationEnum)Enum.Parse(typeof(AnalysisModel.AxisLocationEnum), eixo);
        am.AnalysisEngine = "Tekla Structural Designer";
        am.Insert();
        if (am.ID == null || am.ID.ID <= 0) { Console.WriteLine("ERRO: o Tekla recusou criar o modelo de cálculo"); return 5; }
        var handler = new AnalysisModelHandler();
        var nossoId = new Dictionary<int, string>();
        ModelObjectEnumerator en = m.GetModelObjectSelector().GetAllObjectsWithType(ModelObject.ModelObjectEnum.BEAM);
        int n = 0;
        while (en.MoveNext())
        {
            Beam b = en.Current as Beam;
            if (b == null) continue;
            string c = "", id = "";
            b.GetUserProperty("comment", ref c);
            if (c != MARCA) continue;
            b.GetUserProperty("USER_FIELD_1", ref id);
            nossoId[b.Identifier.ID] = id;
            handler.AddPart(am, b); n++;
        }
        m.CommitChanges();
        am.Select(true);
        Console.WriteLine("peças no modelo de cálculo: " + n);
        var nos = new List<object>();
        AnalysisObjectEnumerator ne = am.AnalysisNodes;
        while (ne != null && ne.MoveNext())
        {
            AnalysisNode no = ne.Current as AnalysisNode;
            if (no == null) continue;
            nos.Add(new Dictionary<string, object> { { "pos", V3(no.Position) }, { "usuario", no.IsUserNode },
                { "apoio", no.Support != null && no.Support.Support != null ? no.Support.Support.Select(s => s.ToString()).ToArray() : null } });
        }
        var pecas = new List<object>();
        AnalysisObjectEnumerator pe = am.AnalysisParts;
        while (pe != null && pe.MoveNext())
        {
            AnalysisPart ap = pe.Current as AnalysisPart;
            if (ap == null) continue;
            var barras = new List<object>();
            foreach (AnalysisBar bar in ap.GetAnalysisBars())
            {
                var pos = new List<object>();
                foreach (AnalysisPosition q in bar.GetPositions())
                    pos.Add(new Dictionary<string, object> { { "tipo", q.Type.ToString() }, { "no", q.Node == null ? null : V3(q.Node.Position) } });
                var membros = new List<object>();
                foreach (AnalysisMember mb in bar.GetMembers())
                    membros.Add(new Dictionary<string, object> { { "inicio", Ponta(mb.Start) }, { "fim", Ponta(mb.End) } });
                barras.Add(new Dictionary<string, object> { { "posicoes", pos }, { "membros", membros }, { "secao", Secao(bar.ProfileStart) },
                                                            { "tipo", bar.AnalysisType.ToString() } });
            }
            string idn;
            nossoId.TryGetValue(ap.PartID.ID, out idn);
            pecas.Add(new Dictionary<string, object> { { "id", idn }, { "nome", ap.PartName }, { "secao", Secao(ap.Profile) },
                { "eixo_x", V3(ap.CoordinateSystem == null ? null : ap.CoordinateSystem.AxisX) }, { "barras", barras } });
        }
        var issues = new List<string>();
        try { foreach (var i in am.GetIssues()) issues.Add(i.ToString()); } catch (Exception) { }
        var js = new JavaScriptSerializer { MaxJsonLength = int.MaxValue };
        File.WriteAllText(saida, js.Serialize(new Dictionary<string, object> { { "modelo", am.AnalysisModelName }, { "eixo", eixo },
            { "nos", nos }, { "pecas", pecas }, { "avisos", issues } }), new UTF8Encoding(false));
        Console.WriteLine(string.Format("modelo de cálculo do Tekla: {0} nós, {1} peças -> {2}", nos.Count, pecas.Count, saida));
        return 0;
    }

    static int Ler(Model m, string saida)
    {
        var pecas = new List<Dictionary<string, object>>();
        ModelObjectEnumerator en = m.GetModelObjectSelector().GetAllObjectsWithType(ModelObject.ModelObjectEnum.BEAM);
        while (en.MoveNext())
        {
            Beam b = en.Current as Beam;
            if (b == null) continue;
            string c = "", id = "";
            b.GetUserProperty("comment", ref c);
            if (c != MARCA) continue;
            b.GetUserProperty("USER_FIELD_1", ref id);
            string marca = "";
            b.GetReportProperty("PART_POS", ref marca);
            CoordinateSystem cs = b.GetCoordinateSystem();
            var d = new Dictionary<string, object>();
            d["id"] = id;
            d["perfil"] = b.Profile.ProfileString;
            d["posicao"] = marca;
            foreach (string k in new[] { "LENGTH", "WEIGHT", "WEIGHT_NET", "WEIGHT_GROSS", "PROFILE_WEIGHT", "AREA", "AREA_NET", "VOLUME", "MATERIAL.DENSITY",
                                         "PROFILE.WEIGHT_PER_UNIT_LENGTH", "PROFILE.CROSS_SECTION_AREA", "PROFILE.MOMENT_OF_INERTIA_X",
                                         "PROFILE.MOMENT_OF_INERTIA_Y", "PROFILE.TORSIONAL_CONSTANT", "PROFILE.WARPING_CONSTANT",
                                         "PROFILE.SECTION_MODULUS_X", "PROFILE.SECTION_MODULUS_Y", "PROFILE.RADIUS_OF_GYRATION_X",
                                         "PROFILE.RADIUS_OF_GYRATION_Y", "PROFILE.POLAR_RADIUS_OF_GYRATION", "PROFILE.COVER_AREA",
                                         "PROFILE.TANGENT_OF_PRINCIPAL_AXIS_ANGLE", "COG_X", "COG_Y", "COG_Z" })
                d[k] = Rp(b, k);
            d["eixo_x"] = new[] { cs.AxisX.GetNormal().X, cs.AxisX.GetNormal().Y, cs.AxisX.GetNormal().Z };
            d["eixo_y"] = new[] { cs.AxisY.GetNormal().X, cs.AxisY.GetNormal().Y, cs.AxisY.GetNormal().Z };
            pecas.Add(d);
        }
        var js = new JavaScriptSerializer { MaxJsonLength = int.MaxValue };
        File.WriteAllText(saida, js.Serialize(new Dictionary<string, object> { { "pecas", pecas } }), new UTF8Encoding(false));
        Console.WriteLine("lidas " + pecas.Count + " peças -> " + saida);
        return 0;
    }
}
