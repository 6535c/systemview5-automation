using System;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Collections.Generic;
using System.Web.Script.Serialization;
public class SvCom {
 static object Get(object o,string name,params object[] args){return o.GetType().InvokeMember(name,BindingFlags.GetProperty,null,o,args);}
 static object Try(object o,string name){try{return Get(o,name);}catch{return null;}}
 static object Form(object forms,string name){int n=Convert.ToInt32(Get(forms,"Count"));object fallback=null;for(int i=0;i<n;i++){object f=Get(forms,"Item",i);if(name.StartsWith("@")){if(Convert.ToBoolean(Try(f,"Visible")??false)&&Convert.ToString(Try(f,"hWnd"))==name.Substring(1))return f;continue;}if(Convert.ToString(Get(f,"Name"))!=name)continue;fallback=f;if(Convert.ToBoolean(Try(f,"Visible")??false))return f;}if(fallback!=null)return fallback;throw new Exception("Form not loaded: "+name);}
 [STAThread] public static void Main(string[] args){
  Console.OutputEncoding=new System.Text.UTF8Encoding(false);
  try {
   object forms=Marshal.BindToMoniker(Path.GetFullPath(args[0]));object result=null;
   if(args.Length==1){var list=new List<object>();int count=Convert.ToInt32(Get(forms,"Count"));for(int i=0;i<count;i++){var f=Get(forms,"Item",i);list.Add(new {name=Get(f,"Name"),hwnd=Try(f,"hWnd")});}result=list;}
   else if(args.Length>=3&&args[2]=="tabs"){
    object form=Form(forms,args[1]);object strip=Get(form,"TabStrip1");object tabs=Get(strip,"Tabs");int n=Convert.ToInt32(Get(tabs,"Count"));var list=new List<object>();for(int i=1;i<=n;i++){object t=Get(tabs,"Item",i);list.Add(new {index=i,caption=Try(t,"Caption"),selected=Try(t,"Selected")});}result=list;
   }
   else if(args.Length>=4&&args[2]=="tab"){
    object form=Form(forms,args[1]);object strip=Get(form,"TabStrip1");object tabs=Get(strip,"Tabs");object t=Get(tabs,"Item",Int32.Parse(args[3]));t.GetType().InvokeMember("Selected",BindingFlags.SetProperty,null,t,new object[]{true});result=Try(t,"Selected");
   }
   else if(args.Length>=4&&args[2]=="click"){
    object form=Form(forms,args[1]);object controls=Get(form,"Controls");int n=Convert.ToInt32(Get(controls,"Count"));bool found=false;
    for(int i=0;i<n;i++){object c=Get(controls,"Item",i);if(Convert.ToString(Get(c,"Name"))!=args[3])continue;if(args.Length>4&&Convert.ToString(Try(c,"Index"))!=args[4])continue;
     c.GetType().InvokeMember("Value",BindingFlags.SetProperty,null,c,new object[]{false});
     c.GetType().InvokeMember("Value",BindingFlags.SetProperty,null,c,new object[]{true});
     // Click may unload the form and destroy this control. Do not read it back.
     result=true;found=true;break;
    }if(!found)throw new Exception("Control not found");
   }
   else if(args.Length>=5&&(args[2]=="text"||args[2]=="value")){
    object form=Form(forms,args[1]);object controls=Get(form,"Controls");int n=Convert.ToInt32(Get(controls,"Count"));bool found=false;
    string property=args[2]=="value"?"Value":"Text";object value=args[2]=="value"?(object)Boolean.Parse(args[4]):args[4];
    for(int i=0;i<n;i++){object c=Get(controls,"Item",i);if(Convert.ToString(Get(c,"Name"))!=args[3])continue;if(args.Length>5&&Convert.ToString(Try(c,"Index"))!=args[5])continue;c.GetType().InvokeMember(property,BindingFlags.SetProperty,null,c,new object[]{value});result=Get(c,property);found=true;break;}if(!found)throw new Exception("Control not found");
   }
   else if(args.Length>=4&&args[2]=="focus"){
    object form=Form(forms,args[1]);object controls=Get(form,"Controls");int n=Convert.ToInt32(Get(controls,"Count"));bool found=false;
    for(int i=0;i<n;i++){object c=Get(controls,"Item",i);if(Convert.ToString(Get(c,"Name"))!=args[3])continue;if(args.Length>4&&Convert.ToString(Try(c,"Index"))!=args[4])continue;c.GetType().InvokeMember("SetFocus",BindingFlags.InvokeMethod,null,c,new object[0]);found=true;break;}if(!found)throw new Exception("Control not found");result=true;
   }
   else if(args.Length>=3&&args[2]=="buttons"){
    object form=Form(forms,args[1]);object bar=Get(form,args.Length>3?args[3]:"SysToolbar");object buttons=Get(bar,"Buttons");var list=new List<object>();int n=Convert.ToInt32(Get(buttons,"Count"));
    for(int i=1;i<=n;i++){object b=Get(buttons,"Item",i);var row=new Dictionary<string,object>();foreach(string prop in new string[]{"Index","Key","Caption","ToolTipText","Left","Top","Width","Height","Value","Enabled"})row[prop]=Try(b,prop);list.Add(row);}result=list;
   }
   else if(args.Length>=4&&args[2]=="call"){
    object form=Form(forms,args[1]);var vals=new List<object>();for(int i=4;i<args.Length;i++){int n;bool b;vals.Add(Int32.TryParse(args[i],out n)?(object)n:Boolean.TryParse(args[i],out b)?(object)b:args[i]);}
    result=form.GetType().InvokeMember(args[3],BindingFlags.InvokeMethod,null,form,vals.ToArray());
   }
   else {
    object form=Form(forms,args[1]);object controls=Get(form,"Controls");var list=new List<object>();int count=Convert.ToInt32(Get(controls,"Count"));
    for(int i=0;i<count;i++){object c=Get(controls,"Item",i);var row=new Dictionary<string,object>();foreach(string name in new string[]{"Name","Index","Caption","hWnd","Left","Top","Width","Height","Visible","Value","ToolTipText"})row[name]=Try(c,name);object parent=Try(c,"Container");if(parent!=null)row["Container"]=Try(parent,"Name");list.Add(row);}result=list;
   }
   Console.WriteLine(new JavaScriptSerializer().Serialize(result));
  }catch(Exception e){Console.Error.WriteLine(e.ToString());Environment.ExitCode=1;}
 }
}
