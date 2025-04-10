import argparse
import os
import re
import shutil
import subprocess
import zipfile


class  SmaliInject:
    def __init__(self,args):
        self.apkpath = args.input
        self.outdir = args.output
        self.deletelist = []
        self.toolPath = os.getcwd() + r"\tools"
        self.decompileDir = os.getcwd() + r"\decompile"
        self.dexPath = os.getcwd() + r"\dex"
        self.dexList = []
        apkfile = zipfile.ZipFile(self.apkpath, 'r')
        for file_name in apkfile.namelist():
            if file_name.endswith(".dex") and file_name.startswith("classes"):
                if not os.path.exists(self.dexPath):
                    os.mkdir(self.dexPath)
                apkfile.extract(file_name, self.dexPath)
                self.dexList.append(os.path.join(self.dexPath, file_name))

    def injectso(self):
        target_activity = self.get_launchable_activity_aapt()
        print(target_activity)
        for dex in self.dexList:
            print(dex)
            if self.dexDecompile(dex):
                smali_path = os.path.join(self.decompileDir,target_activity.replace('.','\\'))+".smali"
                if os.path.exists(smali_path):
                    print(smali_path)
                    with open(smali_path, 'r') as fp:
                        lines = fp.readlines()
                        has_clinit = False
                        start = 0
                        for i in range(len(lines)):
                            if lines[i].find(".source") != -1:
                                start = i
                            if lines[i].find(".method static constructor <clinit>()V") != -1:
                                if lines[i + 3].find(".line") != -1:
                                    code_line = lines[i + 3][-3:]
                                    lines.insert(i + 3, "%s%s\r" % (lines[i + 3][0:-3], str(int(code_line) - 2)))
                                    print("%s%s" % (lines[i + 3][0:-3], str(int(code_line) - 2)))
                                    lines.insert(i + 4, "const-string v0, \"xx-g\"\r")
                                    lines.insert(i + 5,
                                                "invoke-static {v0}, Ljava/lang/System;->loadLibrary(Ljava/lang/String;)V\r")
                                    has_clinit = True
                                    print("add load frida gadget method static constructor <clinit>()V 1")
                                    break
                        if not has_clinit:
                            lines.insert(start + 1, ".method static constructor <clinit>()V\r")
                            lines.insert(start + 2, ".registers 1\r")
                            lines.insert(start + 3, ".line 10\r")
                            lines.insert(start + 4, "const-string v0, \"xx-g\"\r")
                            lines.insert(start + 5,
                                        "invoke-static {v0}, Ljava/lang/System;->loadLibrary(Ljava/lang/String;)V\r")
                            lines.insert(start + 6, "return-void\r")
                            lines.insert(start + 7, ".end method\r")
                            print("add load frida gadget method static constructor <clinit>()V 2")

                        with open(smali_path, "w") as fp:
                            fp.writelines(lines)
                    self.dexCompile(dex)
                    break

    def modifyapk(self):
        (path, filename) = os.path.split(self.apkpath)
        (file, ext) = os.path.splitext(filename)
        outapk = os.path.join(self.outdir, file + "_frida.apk")
        with zipfile.ZipFile(self.apkpath, 'r')as orig_file:
            with zipfile.ZipFile(outapk, 'w')as out_file:
                for item in orig_file.infolist():
                    if item.filename.startswith("classes") and item.filename.endswith(".dex"):
                        continue
                    if item.filename.find("META-INF") == -1 :
                        out_file.writestr(item, orig_file.read(item.filename))
                for dex in self.dexList:
                    out_file.write(dex,os.path.split(dex)[1])
                out_file.write(os.path.join(self.toolPath, "frida-gadget-16.5.9-android-arm64.so"),
                               arcname="lib/arm64-v8a/libxx-g.so")
                print("add lib/arm64-v8a/libfrida-gadget.so")
        shutil.rmtree("dex")
        shutil.rmtree("decompile")
        return outapk

    def addHook(self,apk_path):
        with zipfile.ZipFile(apk_path, 'a')as apk_file:
            for item in apk_file.infolist():
                if item.filename == "lib/arm64-v8a/libxx-g.so":
                    apk_file.write(os.path.join(self.toolPath, "libfrida-gadget.config.so"),
                                   arcname="lib/arm64-v8a/libxx-g.config.so")
                    print("add lib/arm64-v8a/libfrida-gadget.config.so")
                continue

    def signApk(self,apk_path):
        keystore = os.path.join(self.toolPath,'APPkeystore.jks')
        alias = 'key0'
        pswd = 'qwer1234'
        aliaspswd = 'qwer1234'

        apkname = os.path.splitext(os.path.split(apk_path)[1])[0]
        outfile = os.path.join(os.path.split(apk_path)[0], apkname + "_Signed.apk")

        cmd = 'java -jar %s\\apksigner.jar sign --ks %s --ks-key-alias %s --ks-pass pass:%s --key-pass pass:%s --out %s %s'% \
              (self.toolPath,keystore, alias,pswd,aliaspswd,outfile,apk_path)
        os.system(cmd)

    def get_launchable_activity_aapt(self):

        aapt_path = os.path.join(self.toolPath, 'aapt2.exe')
        cmd = '%s dump badging "%s" ' % (aapt_path, self.apkpath)
        p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        out,err = p.communicate()
        cmd_output = out.decode('utf-8').split('\r')
        for line in cmd_output:
            pattern = re.compile("launchable-activity: name='(\S+)'")
            match = pattern.search(line)
            if match:
                # print match.group()[27:-1]
                return match.group()[27:-1]
    def dexCompile(self,dexPath):
        baksmaliJarPath = os.path.join(self.toolPath, "smali-2.5.2.jar")
        command = 'java -jar \"%s\" assemble -o \"%s\" \"%s\"' % (baksmaliJarPath, dexPath, self.decompileDir)
        os.system(command)
        if not os.path.exists(dexPath):
            print(u"反编译失败")
    def dexDecompile(self,dexPath):
        if os.path.exists(self.decompileDir):
            shutil.rmtree(self.decompileDir)
        baksmaliJarPath = os.path.join(self.toolPath, "baksmali-2.5.2.jar")
        if not os.path.exists(dexPath):
            print(u"[dexDecompile] 文件%s不存在", dexPath)
            return False
        if not os.path.exists(baksmaliJarPath):
            print(u"[dexDecompile] 文件%s不存在", baksmaliJarPath)
            return False
        command = 'java -jar \"%s\" disassemble -o \"%s\" \"%s\"' % (baksmaliJarPath, self.decompileDir, dexPath)
        os.system(command)
        if not os.path.exists(self.decompileDir):
            print(u"[dexDecompile] 路径%s不存在", self.decompileDir)
            return False
        return True


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument('input', help="apk path")
    parser.add_argument('output', help="Folder to store output files")
    parser.add_argument('-apksign', help="Sign apk", action='store_true')
    parser.add_argument('-persistence', help="HOOK Persistence ", action='store_true')

    args = parser.parse_args()
    tool = SmaliInject(args)
    tool.injectso()
    out = tool.modifyapk()
    if args.persistence:
        tool.addHook(out)
    if args.apksign:
        tool.signApk(out)


    print(u"sucess, new apk :"+out)